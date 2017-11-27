# coding=utf-8
# 导入蓝图对象api
from . import api
# 导入redis数据库实例
from ehome import redis_store,constants,db
# 导入flask内置的对象
from flask import current_app,jsonify,g,request
# 导入模型类
from ehome.models import Area,House,Facility,HouseImage
# 导入自定义的状态码
from ehome.utils.response_code import RET
# 导入登陆验证装饰器
from ehome.utils.commons import login_required
# 导入七牛云
from ehome.utils.image_storage import storage

# 导入json模块
import json


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





















