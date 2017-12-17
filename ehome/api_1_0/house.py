# coding=utf-8


# 导入蓝图对象api
from . import api
# 导入redis数据库实例
from ehome import redis_store,constants,db
# 导入flask内置的模块或方法
from flask import current_app,jsonify,request,g,session
# 导入模型类
from ehome.models import Area,House,Facility,HouseImage,User,Order
# 导入自定义的状态码
from ehome.utils.response_code import RET
# 导入登陆验证装饰器
from ehome.utils.commons import login_required
# 导入七牛云
from ehome.utils.image_storage import storage

# 导入json模块
import json
# 导入datetime模块,对日期参数进行格式化
import datetime



@api.route('/areas',methods=['GET'])
def get_area_info():
    """
    获取区域信息
    首页区域信息加载----缓存数据库-----磁盘数据库----缓存数据库
    1. 尝试从redis 数据库中获取缓存的区域信息
    2. 如果获取过程发生异常，要把获取结果重新置为None值
    3. 判断获取结果，如果有数据直接返回，可留下房屋缓存数据的日志信息
    4. 查询mysql数据库，获取区域信息
    5. 校验查询结果
    6. 对查询结果进行保存，遍历查询结果，调用模型类实例方法，添加区域信息
    7. 序列化数据，转为json,存入缓存中
    8. 拼接字符串，直接返回区域信息的json数据
    :return:
    """
    # 先尝试从redis缓存中获取区域信息
    try:
        ret = redis_store.get('area_info')
    except Exception as e:
        current_app.logger.error(e)
        # 把ret重新置为None值
        ret = None
    # 判断获取结果
    if ret:
        # 记录访问redis数据库房屋区域信息的时间
        current_app.logger.info('hit area info redis')
        # 直接返回区域信息数据
        return '{"errno":0, "errmsg":"OK", "data":%s}' %ret
    # 查询mysql数据库，获取区域信息
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='获取区域信息失败')
    # 判断查询结果
    if not areas:
        return jsonify(errno=RET.NODATA, errmsg='无区域信息')
    # 定义列表存储查询结果
    areas_list = []
    # 遍历查询结果，调用模型类的实例方法，添加区域信息数据
    for area in areas:
        areas_list.append(area.to_dict())
    # 转为json字符串，准备存入缓存中
    areas_json = json.dumps(areas_list)
    try:
        redis_store.setex('area_info', constants.AREA_INFO_REDIS_EXPIRES,areas_json)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='缓存区域信息异常')
    # 返回区域信息的json数据
    resp = '{"errno":0, "errmsg":"OK","data":%s}' % areas_json
    return resp


@api.route('/houses',methods=['POST'])
@login_required
def save_house_info():
    """
    发布新房屋:获取参数、校验参数、查询数据、返回结果
    1. 获取参数，user_id = g.user_id, 获取post请求的房屋数据
    2. 验证参数的存在
    3. 获取详细的参数信息，主要包括房屋的基本字段
    4. 对参数的校验，对价格进行单位转换，由元转成分
    5. 保存房屋数据，构造模型类对象，存储房屋的基本信息，db.session.add(house)
    6. 尝试获取配套设施信息，如果有数据，对设施进行过滤操作
    7. 存储配套设施信息，house.facilities = facilities
    8. 提交数据到数据库
    9. 返回结果，需要返回房屋id
    :return:
    """
    # 获取参数user_id, 房屋基本数据
    user_id = g.user_id
    # 存储房屋数据post请求的参数
    house_data = request.get_json()
    # 检验参数的存在
    if not house_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 获取详细的房屋参数信息
    # 房屋标题
    title = house_data.get('title')
    # 房屋价格
    price = house_data.get('price')
    # 房屋区域
    area_id = house_data.get('area_id')
    # 房屋地址
    address = house_data.get('address')
    # 房间数目
    room_count = house_data.get('room_count')
    # 房屋面积
    acreage = house_data.get('acreage')
    # 房屋户型
    unit = house_data.get('unit')
    # 房屋适住人数
    capacity = house_data.get('capacity')
    # 房屋卧床配置
    beds = house_data.get('beds')
    # 房屋押金
    deposit = house_data.get('deposit')
    # 最小入住天数
    min_days = house_data.get('min_days')
    # 最大入住天数
    max_days = house_data.get('max_days')
    # 校验参数的完整性
    if not all([title, price, area_id, address, room_count,acreage,unit,capacity,beds,deposit,min_days,max_days]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
    # 对参数处理，转换价格单位，前端使用元为单位，后端数据库中存储的是分为单位，所以需要转换单位
    try:
        price = int(float(price)*100)
        deposit = int(float(deposit)*100)

    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg='价格参数异常')
    # 先保存房屋基本信息
    house = House()
    house.title = title
    house.user_id = user_id
    house.area_id = area_id
    house.price = price
    house.address =address
    house.room_count =room_count
    house.deposit = deposit
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.acreage = acreage
    house.min_days = min_days
    house.max_days = max_days
    # 处理房屋配套设施，尝试获取配套设施的参数信息
    facility = house_data.get('facility')
    # 判断配置设施存在
    if facility:
        # 过滤配套设施标号，in_判断用户传入的设施编号在模型类中存在
        try:
            facilities = Facility.query.filter(Facility.id.in_(facility)).all()
            # 保存房屋设施信息
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR,errmsg='查询配套设施异常')

    # 提交数据到数据库
    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 提交数据发生异常需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存房屋信息失败')
    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK', data={'house_id':house.id})


# 保存房屋图片
@api.route('/houses/<int:house_id>/images', methods=['POST'])
@login_required
def save_house_image(house_id):
    """
    保存房屋图片
    1. 获取参数，获取用户上传的房屋图片request.files.get('house_image')
    2. 通过house_id,保存房屋图片，查询数据库确定房屋存在
    3. 校验查询结果
    4. 读取图片数据
    5. 调用七牛云接口，上传房屋图片
    6. 保存房屋图片，house_image = HouseImage()
    7. 保存房屋图片到房屋表，主图片设置判断
    8. 提交数据到数据库，如果发生异常需要进行回滚
    9. 拼接路径，返回前端图片url

    :param house_id:
    :return:
    """
    # 获取参数图片文件
    image = request.files.get('house_image')
    # 校验参数
    if not image:
        return jsonify(errno=RET.PARAMERR,errmsg='图片未上传')
    # 检验房屋存在
    try:
        house = House.query.filter_by(id=house_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据异常')
    # 校验查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='房屋不存在')

    # 读取图片数据
    image_data = image.read()
    # 调用七牛云接口
    try:
        image_name = storage(image_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='七牛上传图片失败')
    # 存储图片数据到mysql数据库中
    house_image = HouseImage()
    house_image.house_id =house_id
    house_image.url = image_name
    # 把图片数据加入到数据库会话对象中，HouseImage()模型类
    db.session.add(house_image)
    # 判断房屋主图片是否设置，因为首页需要展示房屋幻灯片信息，添加主图片设置
    if not house.index_image_url:
        house.index_image_url = image_name
        # 把图片数据加入到数据库会话对象中，House()模型类
        db.session.add(house)
    # 提交数据到数据库中
    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 存储数据发生异常，需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='存储房屋图片异常')
    # 拼接图片的绝对路径，返回前端
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    return jsonify(errno=RET.OK, errmsg='OK', data={'url':image_url})


@api.route("/user/houses",methods=['GET'])
@login_required
def get_user_houses():
    """
    获取用户发布房屋信息
    1/获取取参数,user_id
    2/根据用户id查询数据库,使用反向引用查询该用户发布的所有房屋信息
    3/定义列表,如果有数据,存储查询结果,调用模型类的方法to_basic_dict()
    4/返回结果
    :return:
    """
    # 获取参数
    user_id = g.user_id
    # 查询mysql数据库
    try:
        user = User.query.get(user_id)
        # 使用反向引用,获取该用户发布的房屋信息,一对多的查询
        houses = user.houses
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户房屋信息失败')
    # 定义列表,准备存储查询结果
    houses_list = []
    # 判断查询结果有数据,遍历查询结果,添加房屋基本信息
    if houses is not None:
        for house in houses:
            houses_list.append(house.to_basic_dict())
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'houses':houses_list})


@api.route('/session',methods=['GET'])
def check_login():
    """
    检查用户登陆状态
    1/尝试从redis缓存中获取用户名信息
    2/判断获取结果,如果用户已登陆,返回用户名信息
    3/否则默认返回false
    :return:
    """
    # 使用请求上下文对象,从redis缓存中获取用户名信息
    name = session.get('name')
    # 判断获取结果是否有数据
    if name is not None:
        return jsonify(errno=RET.OK,errmsg='true',data={'name':name})
    else:
        return jsonify(errno=RET.SESSIONERR,errmsg='false')


@api.route('/houses/index',methods=['GET'])
def get_houses_index():
    """
    项目首页信息:缓存----磁盘----缓存
    1/尝试从redis缓存中获取房屋信息
    2/判断获取结果,如果有数据,记录访问时间,直接返回结果
    3/查询mysql数据库
    4/默认按照房屋成交量进行查询,
    houses = House.query.order_by(House.order_count.desc()).limit(5)
    5/判断查询结果
    6/定义列表,遍历查询结果,添加数据,
    7/判断是否设置主图片,如未设置主图片默认不添加
    8/序列化房屋数据
    9/存入到缓存中,
    10/返回结果
    :return:
    """
    #　尝试从redis获取房屋首页幻灯片信息
    try:
        ret = redis_store.get('home_page_data')
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 如果有数据,记录访问缓存数据的时间,直接返回房屋信息
    if ret:
        current_app.logger.info('hit house index info redis')
        return '{"errno":0,"errmsg":"OK","data":%s}' % ret
    # 查询mysql数据库,获取房屋信息,默认按照房屋成交量进行倒叙查询
    try:
        houses = House.query.order_by(House.order_count.desc()).limit(constants.HOME_PAGE_MAX_HOUSES)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋信息失败')
    # 校验查询结果
    if not houses:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 定义列表,遍历查询结果
    houses_list = []
    for house in houses:
        # 判断房屋主图片如未设置,默认不添加数据
        if not house.index_image_url:
            continue
        houses_list.append(house.to_basic_dict())
    # 序列化数据
    houses_json = json.dumps(houses_list)
    # 把房屋数据存入到redis缓存中
    try:
        redis_store.setex('home_page_data',constants.HOME_PAGE_DATA_REDIS_EXPIRES,houses_json)
    except Exception as e:
        current_app.logger.error(e)
    # 返回结果
    resp = '{"errno":0,"errmsg":"Ok","data":%s}' % houses_json
    return resp


@api.route("/houses/<int:house_id>",methods=['GET'])
def get_house_detail(house_id):
    """
    获取房屋详情信息:缓存----磁盘----缓存
    1/获取参数,user_id,把用户分为两类,登陆用户/未登陆用户
    user_id = session.get('user_id','-1')
    2/校验house_id参数
    3/尝试从redis缓存中获取房屋信息
    4/校验结果,如果有数据,
    5/查询mysql数据库
    6/调用模型类的to_full_dict(),进行异常处理
    7/序列化数据
    8/存储到redis缓存中
    9/返回结果
    :return:
    """
    # 使用请求上下文对象session,从redis中获取用户身份信息,如未登陆,默认给-1值
    user_id = session.get('user_id','-1')
    # 校验房屋的存在
    if not house_id:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 尝试从redis中获取房屋信息
    try:
        ret = redis_store.get('house_info_%s' % house_id)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断获取结果
    if ret:
        current_app.logger.info('hit house detail info redis')
        return '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' % (user_id,ret)
    # 查询mysql数据库
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋详情信息失败')
    # 校验查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 调用模型类中方法,获取房屋详情信息
    try:
        house_data = house.to_full_dict()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='获取房屋详情信息异常')
    # 序列化数据
    house_json = json.dumps(house_data)
    # 把房屋详情数据存入缓存中
    try:
        redis_store.setex('house_info_%s' % house_id,constants.HOUSE_DETAIL_REDIS_EXPIRE_SECOND,house_json)
    except Exception as e:
        current_app.logger.error(e)
    # 返回结果
    resp = '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' %(user_id,house_json)
    return resp


@api.route('/houses',methods=['GET'])
def get_houses_list():
    """
    房屋列表页:
    获取参数/校验参数/查询数据/返回结果
    缓存----磁盘----缓存
    1/获取参数,area_id,start_date_str,end_date_str,sort_key,page
    2/参数处理,sort_key给默认值,默认按照房屋发布时间进行排序,page默认加载第一页数据
    3/判断如果有日期参数,对日期进行格式化处理,datetime模块
    4/确认用户选择的开始日期必须小于等于结束结束日期,至少预定1天
    5/对页数进行格式化,page = int(page)
    6/尝试从redis中获取房屋列表信息,每页数据里存储多条数据,需要使用hash数据类型
    ret = redis_store.hget('houses_%s_%s_%s_%s' % (area_id,start_date_str_end_date_str,sort_key))
    7/如果有数据,记录访问房屋列表数据的信息,返回结果
    8/需要查询mysql数据库,
    9/定义查询数据库的过滤条件,params_filter = []主要包括:区域信息/开始日期和结束日期
    10/根据过滤条件查询数据库,按照booking成交量/价格price-inc,price-des/房屋发布时间new;
    houses = House.query.filter(*params_filter).order_by(House.create_time.desc())
    11/对查询结果进行分页,paginate分页返回的结果,包括总页数,房屋数据
    hosues_page = houses.paginate(page,2,False) /False分页如果发生异常不报错
    houses_list = houses_page.items (分页后的房屋数据)
    total_page = houses_page.pages (分页后的总页数)
    12/遍历分页后的房屋数据,获取房屋的基本信息,需要调用模型类中的house_dict_list = to_basic_dict()方法
    13/构造响应数据:
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    14/序列化数据,resp_json = json.dumps(resp)
    15/存入缓存中,设置redis中房屋列表数据,判断用户请求的页数小于等于总页数,即请求的页数是有数据的
    16/对多条数据往redis中存储,需要开启事务,确保数据的完整性和一致性,
    pip = redis_store.pipeline()
    pip.multi()/pip.hset(redis_key,page,resp_json)/pip.expire(redis_key,7200)/pip.execute()
    17/返回结果 return resp_json
    :return:
    """
    # 获取参数,当前接口都是可选参数
    area_id = request.args.get('aid','')
    start_date_str = request.args.get('sd','')
    end_date_str = request.args.get('ed','')
    sort_key = request.args.get('sk','new') # 如未传参默认new,房屋发布时间
    page = request.args.get('p','1') # 如未传参默认1,房屋列表页
    # 首先对日期进行格式化
    try:
        # 存储日期转换后的结果
        start_date,end_date = None,None
        # 判断如有传入开始日期
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str,'%Y-%m-%d')
        # 判断如有传入结束日期:
        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str,'%Y-%m-%d')
        # 如果开始日期和结束日期都存在,判断开始日期小于等于结束日期,即订房的时间必须是1天
        if start_date_str and end_date_str:
            # 断言代码放入try/except中,会被捕获,
            assert start_date <= end_date
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='日期格式错误')
    # 对页数进行格式化
    try:
        page = int(page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='页数格式错误')
    # 尝试从redis中获取房屋列表信息
    try:
        # 存储的数据类型为hash,键里包含区域信息/开始日期/结束日期/排序条件
        redis_key = 'house_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        # 尝试获取redis缓存中的数据,指定键,属性
        ret = redis_store.hget(redis_key,page)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断查询结果,如有数据直接返回
    if ret:
        # 记录访问redis数据的时间
        current_app.logger.info('hit houses list info redis')
        return ret
    # 查询mysql数据库
    try:
        # 定义列表,存储查询房屋数据的过滤条件
        params_filter = []
        # 校验区域信息的存在
        if area_id:
            # a = [1,3,5,7,9]
            # b = 5
            # a.append(a == b) 添加的数据为true或false
            # 返回的结果是sqlalchemy的对象
            params_filter.append(House.area_id == area_id)
        # 对日期进行处理,决定了房屋能否预定,判断用户如果选择了开始日期和结束日期
        if start_date and end_date:
            # 查询有冲突的订单
            conflict_orders = Order.query.filter(Order.begin_date<=end_date,Order.end_date>=start_date).all()
            # 遍历有冲突的订单,获取有冲突的房屋
            conflict_houses_id = [order.house_id for order in conflict_orders]
            # 判断有冲突的房屋是否存在
            if conflict_houses_id:
                # 存入过滤参数中,进行取反操作,获取所有不冲突的房屋
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户只选择了开始日期
        if start_date:
            # 查询开始日期有冲突的订单数据
            conflict_orders = Order.query.filter(Order.end_date>=start_date).all()
            # 遍历有冲突的订单数据
            conflict_houses_id = [order.house_id for order in conflict_orders]
            # 判断有冲突的房屋存在
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户只选择了结束日期
        if end_date:
            conflict_orders = Order.query.filter(Order.begin_date<=end_date).all()
            conflict_houses_id = [order.house_id for order in conflict_orders]
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 过滤条件已经完成,执行查询语句,获取房屋数据,进行排序查询
        # 判断排序条件,按房屋成交排序查询
        if 'booking' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.order_count.desc())
        # 按照房屋价格进行排序
        elif 'price-inc' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.asc())
        elif 'prcie-des' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.desc())
        # 如果用户未选择排序条件,默认按照房屋发布时间进行排序
        else:
            houses = House.query.filter(*params_filter).order_by(House.create_time.desc())
        # 对查询结果进行分页,page:页数,每页条目书,False分页出错,不会报错
        houses_page = houses.paginate(page,constants.HOUSE_LIST_PAGE_CAPACITY,False)
        # 存储分页后的房屋数据
        houses_list = houses_page.items
        # 存储分页后的总页数
        total_page = houses_page.pages
        # 定义列表,存储分页后的数据
        houses_dict_list = []
        # 遍历分页后的数据,调用了模型类方法,获取房屋基本数据
        for house in houses_list:
            houses_dict_list.append(house.to_basic_dict())
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋列表信息失败')
    # 构造响应数据
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    # 序列化数据
    resp_json = json.dumps(resp)
    # 判断用户请求的页数必须有数据
    if page <= total_page:
        # 构造redis_key
        redis_key = 'houses_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        # 使用hash数据类型,对多条数据需要统一操作,使用事务
        pip = redis_store.pipeline()
        try:
            # 开启事务
            pip.multe()
            # 设置数据
            pip.hset(redis_key,page,resp_json)
            # 设置过期时间
            pip.expire(redis_key,constants.HOUSE_LIST_REDIS_EXPIRES)
            # 执行事务
            pip.execute()
        except Exception as e:
            current_app.logger.error(e)
    # 返回结果
    return resp_json



















