# coding=utf-8

# 导入flask内置的上下文
from flask import current_app, jsonify, make_response, request,session
# 导入蓝图api
from . import api
# 导入captcha扩展包，生成图片验证码
from ehome.utils.captcha.captcha import captcha
# 导入redis数据库实例
from ehome import redis_store, constants, db
# 导入自定义的状态码
from ehome.utils.response_code import RET
# 导入云通讯接口，实现发送短信
from ehome.utils import sms
# 导入数据库模型类
from ehome.models import User

# 导入正则模块
import re
# 导入random模块
import random


# 图片验证码
@api.route('/imagecode/<image_code_id>',methods=['GET'])
def generate_image_code(image_code_id):
    """
    生成图片验证码
    1. 调用captcha 扩展包生成图片验证码，name,text, image
    2. 在服务器保存图片验证码内容，在缓存redis数据库中存储
    3. 使用响应对象返回前端图片验证码
    :param image_code_id:
    :return:
    """
    # 生成图片验证码，调用captcha 扩展包
    name, text, image = captcha.generate_captcha()
    # 在服务器redis缓存中存储图片验证码的内容，指定过期时间
    try:
        redis_store.setex('ImageCode_'+ image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        # 日志记录
        current_app.logger.error(e)
        # jsonify 序列化数据
        return jsonify(errno=RET.DBERR, errmsg='保存图片验证码失败')
        # 返回前图片验证码，需要使用响应对象
        # finally是无论是否有异常，都会被执行，else如未异常执行
    else:
        response = make_response(image)
        # 设置响应的数据类型
        response.headers['Content-Type'] = 'image/jpg'
        # 返回前端图片验证码
        return response


# 发送短信
@api.route('/smscode/<mobile>',methods=['GET'])
def send_sms_code(mobile):
    """
    发送短信：获取参数/校验参数/查询数据/返回结果
    1. 获取参数，查询字符串的参数获取，mobile, text, id, request.args.get('text')
    2. 校验参数，首先校验参数存在
    3. 校验手机号，正则表达式，re.match(r'^1[]$',mobile)
    4. 校验图片验证码：获取本地存储的真实图片验证码
    5. 判断获取结果，如果图片验证码过期结束程序
    6. 删除图片验证码
    7. 比较图片验证码：统一转成小写比较图片验证码内容是否一致
    8. 生成短信码： 使用random 模块随机数
    9. 在本地保存短信验证码内容，判断用户是否已注册
    10. 调用云通讯发送信息： 使用异常进行处理
    11. 保存云通讯的发送结果，判断是否发送成功
    12. 返回前端结果

    :param modile: 
    :return: 
    """
    # 获取参数， mobile, text, id
    image_code = request.args.get('text')
    image_code_id = request.args.get('id')
    # 校验参数存在
    # any, all 方法判断所有参数全部存在
    if not all([mobile, image_code, image_code_id]):
        return jsonify(errno= RET.PARAMERR, errmsg='参数缺失')
    # 检验手机号，使用正则模块
    if not re.match(r'1[345789]\d{9}$', mobile):
        return jsonify(errno= RET.PARAMERR, errmsg='手机号格式错误')
    # 校验图片验证码，获取本地存储的真实图片验证码
    try:
        real_image_code = redis_store.get('ImageCode_'+ image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return  jsonify(errno=RET.DBERR, errmsg='查询图片验证码异常')
    # 判断获取结果
    if not real_image_code:
        return jsonify(errno= RET.NODATA, errmsg='图片验证码过期')
    # 图片验证码只能获取一次，无论是否获取到，都必须删除图片验证码
    try:
        redis_store.delete('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
    # 比较图片验证码内容是否一致
    if real_image_code.lower() != image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg='图片验证码错误')
    # 生成短信随机码，使用随机数模块，生成六位数
    sms_code = '%06d'% random.randint(1,999999)
    # 保存短信验证码
    try:
        redis_store.setex('SMSCode_' +mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存短信验证码失败')
    # 写注册的时候在使用
    # # 判断用户是否已注册
    # try:
    #     user = User.query.filter_by(mobile=mobile).first()
    # except Exception as e:
    #     current_app.logger.error(e)
    #     return jsonify(errno=RET.DBERR,errmsg='查询用户信息异常')
    # else:
    #     # 判断查询结果，用户是否注册
    #     if user is not None:
    #         return jsonify(errno=RET.DATAEXIST, errmsg='手机号已注册')

    # 发送短信，调用云通讯接口
    try:
        # 实例化对象
        ccp = sms.CCP()
        # 调用云通讯发送短信方法
        result = ccp.send_template_sms(mobile,[sms_code,constants.SMS_CODE_REDIS_EXPIRES/60],1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='发送短信异常')
    # 判断发送结果
    # if result ==0:
    # 表达式判断，变量写在后面
    if 0 == result:
        return jsonify(errno=RET.OK, errmsg= '发送成功')
    else:
        return jsonify(errno=RET.THIRDERR, errmsg='发送失败')


# 注册
@api.route('/users', methods=['POST'])
def register():
    """
    注册
    1. 获取参数，获取post请求的参数，get_json()
    2. 校验参数存在
    3. 进一步获取详细的参数信息
    4. 校验参数的完整性
    5. 校验手机号格式
    6. 校验短信验证码，获取本地存储的真实的短信验证码
    7. 判断查询结果
    8. 如果有数据,比较短信验证码
    9. 删除已经验证过的短信验证码
    10. 判断用户是否注册过
    11. 保存用户信息，User(name=mobile, mobile=mobile), user.password = password
    12. 提交数据到数据库中，需要进行回滚
    13. 缓存用户信息，user.id, name, mobile
    14. 返回结果，user.to_dict()
    
    :return: 
    """

    # 获取post 请求的参数
    user_data = request.get_json()
    # 判断数据存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 进一步获取详细的参数，mobile, sms_code, password
    # user_data['mobile']
    mobile = user_data.get('mobile')
    sms_code = user_data.get('sms_code')
    password = user_data.get('password')
    # 验证参数的完整性
    if not all([mobile, sms_code, password]):
        return jsonify(errno = RET.PARAMERR, errmsg='参数缺失')
    # 验证手机号
    if not re.match(r'^1[34578]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号格式错误')

    # 判断用户是否已注册
    try:
        user = User.query.filter_by(mobile=mobile).first()

    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询手机信息异常')
    else:
        if user:
            return jsonify(errno=RET.DATAERR, errmsg='手机号已注册')

    # 校验短信验证码
    try:
        real_sms_code = redis_store.get('SMSCode_'+ mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='获取短信验证码异常')

    # 判断查询结果
    if not real_sms_code:
        return jsonify(errno=RET.DATAERR, errmsg='短信验证码过期')

    # 比较短信验证码，前端的短信验证码转为str
    if real_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR, errmsg='短信验证码错误')

    # 删除短信验证码
    try:
        redis_store.delete('SMSCode_' +mobile)
    except Exception as e:
        current_app.logger.error(e)

    # 保存用户信息， name/mobile/password
        user = User(name=mobile, mobile=mobile)
        # 调用模型类中的加密方法
        user.password = password
        # 提交数据到数据库中
        try:
            db.seesion.add(user)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            # 写入数据如果发生错误，需要进行回滚
            db.session.rollback()
            return jsonify(errno=RET.DBERR, errmsg='保存用户信息异常')
        # 缓存用户信息
        session['user_id'] = user.id
        session['name'] = mobile
        session['mobile'] = mobile

        # 返回结果
        return jsonify(errno=RET.OK, errmsg='OK', data=user.to_dict())





































