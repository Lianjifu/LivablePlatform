# coding=utf-8


# 导入flask 内置的模块和方法
from flask import request, jsonify, current_app, session,g
# 导入自定义状态码
from ehome.utils.response_code import RET
# 导入模型类User
from ehome.models import User
# 导入登录验证装饰器
from ehome.utils.commons import  login_required
# 导入蓝图对象api
from . import api
# 导入正则模块
import re
# 导入七牛云接口
from ehome.utils.image_storage import storage
# 导入数据库实例
from ehome import db, constants


# 登录
@api.route('/sessions', methods=['POST'])
def login():
    """
    登录：获取参数/检验参数/查询数据/返回结果
    1. 获取post请求的参数，grt_json()
    2. 检验参数存在
    3. 进一步获取详细的参数信息，mobile，password
    4. 对手机号格式进行检验
    5. 查询数据库，确定用户存在
    6. 检查查询结果，对密码正确性进行检验user.check_password_has(password)
    7. 缓存用户信息，session['user_id']= user.id
    8. 返回结果
    :return: 
    """
    # 获取post请求的参数
    user_data = request.get_json()
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 进一步获取详细的参数信息
    mobile = user_data.get('mobile')
    password = user_data.get('password')
    # 验证参数的完整性
    if not all([mobile, password]):
        return  jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
    # 校验手机号格式
    if not re.match(r'1[3455678]\d{9}$', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号格式错误')
    # 查询数据库，确认用户信息
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e :
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询用户信息异常')
    # 校验查询结果，校验密码，如果用户不存在或者密码错误
    if user is None or not user.check_password(password):
        return  jsonify(errno=RET.DATAERR, errmsg='用户名或密码错误')
    # 缓存用户信息
    session['user_id'] = user.id
    session['name'] = mobile
    session['mobile'] = mobile
    # 返回结果
    return  jsonify(errno=RET.OK, errmsg='OK', data={'user_id':user.id})


# 获取用户信息
@api.route('/user', methods=['GET'])
@login_required
def get_user_profile():
    """
    获取用户信息
    1. 获取用户id
    2. 根据用户id查询数据库，get(), filter_by()
    3. 校验查询结果，判断是否有数据
    4. 返回用户信息
    :return: 
    """
    # 通过g变量获取用户id
    user_id = g.user_id
    # 通过g变量查询用户信息
    try:
        # User.query.filter_by(id=user_id).first()
        user = User.query.get(user_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='获取用户信息异常')

    # 检验查询结果
    if user is None:
        return jsonify(errno=RET.NODATA, errmsg='无效操作')

    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK', data=user.to_dict())


# 设置用户头像信息
@api.route('user/avatar', methods=['POST'])
@login_required
def set_avatar_url():
    """
    设置用户头像信息
    1. 获取参数，avatar, user_id,request.filter.get('avatar')
    2. 检验参数存在
    3. 读取图片数据，data= avatar.read()
    4. 调用七牛云接口，上传用户头像
    5. 保存用户头像信息到数据库
    6. 拼接用户头像图片的完整路径，七牛云外链域名+图片文件名
    7. 返回结果
    :return: 
    """
    # 获取参数
    user_id = g.user_id
    avatar = request.files.get('avatar')
    # 校验参数不存在
    if not avatar:
        return jsonify(errno=RET.PARAMERR, errmsg='图片未上传')
    # 读取图片数据
    avatar_data = avatar.read()
    # 调用七牛云接口，上传用户头像
    try:
        image_name = storage(avatar_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='上传头像失败')
    # 保存用户头像数据
    try:
        # 使用update更新用户信息
        User.query.filter_by(id=user_id).update({'avatar_url':image_name})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 提交数据异常，需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='保存用户头像数据异常')

    # 拼接头像的完整路径
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回数据
    return  jsonify(errno=RET.OK, errmsg='OK', data={'avatar_url':image_url})

# 修改用户信息
@api.route('/user/name', methods=['PUT'])
@login_required
def change_user_profile():
    """
    修改用户信息
    1. 获取参数，user_id, put请求的参数，request.get_json()
    2. 检验参数
    3. 查询数据库，update更新用户信息
    4. 提交数据，如发生异常需要进行回滚操作
    5. 修改缓存中的用户信息session['name'] = name
    6. 返回结果
    :return: 
    """
    # 获取参数
    user_id = g.user_id
    user_data = request.get_json()
    # 校验参数
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 进一步获取用户输入的name数据
    name = user_data.get('name')
    # 校验name 的存在
    if not name:
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 查询数据库，进行更新修改用户信息操作
    try:
        User.query.filter_by(id=user_id).update({'name':name})
        # 提交数据
        db.session.commit()

    except Exception as e:
        current_app.logger.error(e)
        # 发生异常需要进行回滚
        db.session.rollback()
        return  jsonify(errno=RET.DBERR, errmsg='更新用户信息失败')
    # 更新缓存中的用户信息
    session['name'] = name
    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK', data={'name':name})


# 设置用户实名信息
@api.route('user/auth', methods=['POST'])
@login_required
def set_user_auth():
    """
    设置用户实名信息
    1. 获取参数，user_id, post请求的用户真实姓名和身份信息
    2. 校验参数存在
    3. 进一步获取详细的参数信息
    4. 校验参数的完整性
    5. 保护用户的实名信息
    6. 返回结果
    :return: 
    """
    # 获取参数user_id, real_name, id_card
    user_id = g.user_id
    user_data = request.get_json()
    # 判断参数是否存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg='参数错误')
    # 获取详细的用户身份信息
    real_name = user_data.get('real_name')
    id_card = user_data.get('id_card')
    # 校验参数的完整性
    if not all([real_name, id_card]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
    # 查询数据库，保存用户实名信息
    try:
        User.query.filter_by(id=user_id, real_name=None,id_card=None).update({'real_name':real_name})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 发生异常需要进行回滚
        return jsonify(errno=RET.DBERR, errmsg='保存用户实名信息失败')
    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK')

@api.route('/user/auth', methods=['GET'])
@login_required
def get_user_auth():
    """
    获取用户实名信息
    1. 获取参数，user_id = g.user_id
    2. 查询数据库，获取用户信息，存储查询结果
    3. 校验查询结果
    4. 返回结果：user.auth_to_dict()
    :return: 
    """
    # 获取参数
    user_id = g.user_id
    # 查询数据库
    try:
        # User.query.get(user_id)
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询用户实名信息异常')
    # 校验查询结果
    if user is None:
        return  jsonify(errno=RET.DBERR,errmsg='无效操作')
    # 返回结果，调用了模型类中的user.auth_to_dict()
    return jsonify(errno=RET.OK, errmsg='OK', data=user.auth_to_dict())


@api.route('/session', methods=['DELETE'])
@login_required
def logout():
    """
    退出登录
    清除登录用户的缓存信息
    :return: 
    """
    session.clear()
    return jsonify(errno=RET.OK, errmsg='OK')

