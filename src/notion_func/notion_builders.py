# -*- coding: utf-8 -*-
# Notion 相关工具函数，包括notion块构建、属性构建、日期转换和其他工具函数
import calendar
from datetime import datetime
from datetime import timedelta
import hashlib
import os
import re
import requests
import base64
from .notion_db_prop_config import (
    RICH_TEXT,
    URL,
    RELATION,
    NUMBER,
    DATE,
    FILES,
    STATUS,
    TITLE,
    SELECT,
)
import pendulum

MAX_LENGTH = (
    1024  # NOTION 2000个字符限制https://developers.notion.com/reference/request-limits
)

# Notion blocks 构建工具函数
def get_heading(level, content):
    """
    获取标题
    :param level: 标题等级
    :param content: 标题内容
    :return: 标题块
    """
    if content is None:
        content = ""
    if level == 1:
        heading = "heading_1"
    elif level == 2:
        heading = "heading_2"
    else:
        heading = "heading_3"
    return {
        "type": heading,
        heading: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": content[:MAX_LENGTH],
                    },
                }
            ],
            "color": "default",
            "is_toggleable": False,
        },
    }

def get_quote(content):
    """
    获取引言
    :param content: 引言内容
    :return: 引言块
    """
    if content is None:
        content = ""
    return {
        "type": "quote",
        "quote": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": content[:MAX_LENGTH]},
                }
            ],
            "color": "default",
        },
    }

def get_table_of_contents():
    """
    获取目录
    :return: 目录块
    """
    return {
        "type": "table_of_contents", 
        "table_of_contents": {
            "color": "default"
            }
        }

def get_icon(url):
    """
    获取图标
    :param url: 图标链接
    :return: 图标属性
    """
    return {"type": "external", "external": {"url": url}}

def get_embed(url):
    """
    获取嵌入
    :param url: 嵌入URL
    :return: 嵌入
    """
    return {"type": "embed", "embed": {"url": url}}


def get_block(content,type,show_color, style, colorStyle, reviewId):
    """
    获取区块
    :param content: 块内容
    :param type: 块类型
    :param show_color: 是否显示颜色
    :param style: 划线样式
    :param colorStyle: 划线颜色
    :param reviewId: 笔记id
    :return: 区块
    """
    if content is None:
        content = ""
    color = "default"
    if show_color:
        # 根据划线颜色设置文字的颜色
        if colorStyle == 1:
            color = "red"
        elif colorStyle == 2:
            color = "purple"
        elif colorStyle == 3:
            color = "blue"
        elif colorStyle == 4:
            color = "green"
        elif colorStyle == 5:
            color = "yellow"
    block = {
        "type": type,
        type: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": content[:MAX_LENGTH],
                    },
                }
            ],
            "color": color,
        },
    }
    if(type=="callout"):
        # 根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2
        emoji = "〰️"
        if style == 0:
            emoji = "💡"
        elif style == 1:
            emoji = "⭐"
        # 如果reviewId不是空说明是笔记
        if reviewId != None:
            emoji = "✍️"
        block[type]["icon"] = {"emoji": emoji}
    return block

# Notion Database property 构建工具函数
def get_title(content):
    """
    获取标题属性
    :param content: 标题内容
    :return: 标题属性
    """
    if content is None:
        content = ""
    return {"title": [{"type": "text", "text": {"content": content[:MAX_LENGTH]}}]}

def get_rich_text(content):
    """
    获取富文本属性
    :param content: 富文本内容
    :return: 富文本属性
    """
    if content is None:
        content = ""
    return {"rich_text": [{"type": "text", "text": {"content": content[:MAX_LENGTH]}}]}

def get_url(url):
    """
    获取链接属性
    :param url: 链接
    :return: 链接属性
    """
    return {"url": url}

def get_relation(ids):
    """
    获取关联属性
    :param ids: 关联id
    :return: 关联属性
    """
    return {"relation": [{"id": id} for id in ids]}

def get_number(number):
    """
    获取数字属性
    :param number: 数字
    :return: 数字属性
    """
    return {"number": number}

def get_file(url):
    """
    获取文件属性
    :param url: 文件链接
    :return: 文件属性
    """
    return {"files": [{"type": "external", "name": "Cover", "external": {"url": url}}]}


def get_select(name):
    """
    获取选择属性
    :param name: 选择内容
    :return: 选择属性
    """
    return {"select": {"name": name}}

def get_multi_select(names):
    """
    获取多选属性
    :param names: 多选内容
    :return: 多选属性
    """
    return {"multi_select": [{"name": name} for name in names]}

def get_date(start, end=None):
    """
    获取日期属性
    :param start: 开始日期
    :param end: 结束日期
    :return: 日期属性
    """
    return {
        "date": {
            "start": start,
            "end": end,
            "time_zone": "Asia/Shanghai",
        }
    }

def get_properties(dict1, dict2):
    """
    获取属性
    :param dict1: 属性内容
    :param dict2: 属性类型
    :return: 属性
    """
    properties = {}
    for key, value in dict1.items():
        type = dict2.get(key)
        if value == None:
            continue
        property = None
        if type == TITLE:
            if value is None:
                value = ""
            property = {
                "title": [{"type": "text", "text": {"content": value[:MAX_LENGTH]}}]
            }
        elif type == RICH_TEXT:
            if value is None:
                value = ""
            property = {
                "rich_text": [{"type": "text", "text": {"content": value[:MAX_LENGTH]}}]
            }
        elif type == NUMBER:
            property = {"number": value}
        elif type == STATUS:
            property = {"status": {"name": value}}
        elif type == FILES:
            property = {
                "files": [
                    {"type": "external", "name": "Cover", "external": {"url": value}}
                ]
            }
        elif type == DATE:
            property = {
                "date": {
                    "start": pendulum.from_timestamp(
                        value, tz="Asia/Shanghai"
                    ).to_datetime_string(),
                    "time_zone": "Asia/Shanghai",
                }
            }
        elif type == URL:
            property = {"url": value}
        elif type == SELECT:
            property = {"select": {"name": value}}
        elif type == RELATION:
            property = {"relation": [{"id": id} for id in value]}
        if property:
            properties[key] = property
    return properties


def get_rich_text_from_result(result, name):
    """
    从结果中获取富文本属性
    :param result: 结果
    :param name: 属性名
    :return: 富文本属性
    """
    return result.get("properties").get(name).get("rich_text")[0].get("plain_text")


def get_number_from_result(result, name):
    """
    从结果中获取数字属性
    :param result: 结果
    :param name: 属性名
    :return: 数字属性
    """
    return result.get("properties").get(name).get("number")

def get_property_value(property):
    """
    从Property中获取值
    :param property: 属性
    :return: 属性值
    """
    type = property.get("type")
    content = property.get(type)
    if content is None:
        return None
    if type == "title" or type == "rich_text":
        if len(content) > 0:
            return content[0].get("plain_text")
        else:
            return None
    elif type == "status" or type == "select":
        return content.get("name")
    elif type == "files":
        # 不考虑多文件情况
        if len(content) > 0 and content[0].get("type") == "external":
            return content[0].get("external").get("url")
        else:
            return None
    elif type == "date":
        return str_to_timestamp(content.get("start"))
    else:
        return content

# Notion date/time 处理工具函数
def format_time(time):
    """
    将秒格式化为 xx时xx分格式
    :param time: 秒数
    :return: xx时xx分格式
    """
    result = ""
    hour = time // 3600
    if hour > 0:
        result += f"{hour}时"
    minutes = time % 3600 // 60
    if minutes > 0:
        result += f"{minutes}分"
    return result


def format_date(date, format="%Y-%m-%d %H:%M:%S"):
    """
    将date转换为指定格式
    :param date: date
    :param format: 格式
    :return: 格式化后的date
    """
    return date.strftime(format)


def timestamp_to_date(timestamp):
    """时间戳转化为date
    :param timestamp: 时间戳
    :return: date
    """
    return datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)

def str_to_timestamp(date):
    if date == None:
        return 0
    dt = pendulum.parse(date)
    # 获取时间戳
    return int(dt.timestamp())

def get_first_and_last_day_of_month(date):
    """
    获取给定日期所在月的第一天
    :param date: date
    :return: 第一天，最后一天
    """
    first_day = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 获取给定日期所在月的最后一天
    _, last_day_of_month = calendar.monthrange(date.year, date.month)
    last_day = date.replace(
        day=last_day_of_month, hour=0, minute=0, second=0, microsecond=0
    )

    return first_day, last_day

def get_first_and_last_day_of_year(date):
    """
    获取给定日期所在年的第一天和最后一天
    :param date: date
    :return: 第一天，最后一天
    """
    first_day = date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # 获取给定日期所在年的最后一天
    last_day = date.replace(month=12, day=31, hour=0, minute=0, second=0, microsecond=0)

    return first_day, last_day

def get_first_and_last_day_of_week(date):
    """
    获取给定日期所在周的第一天和最后一天
    :param date: date
    :return: 第一天（周一），最后一天（周日）
    """
    first_day_of_week = (date - timedelta(days=date.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    last_day_of_week = first_day_of_week + timedelta(days=6)

    return first_day_of_week, last_day_of_week

def get_days_between(start_timestamp, end_timestamp):
    start_date = pendulum.from_timestamp(start_timestamp, tz="Asia/Shanghai").start_of('day')
    end_date = pendulum.from_timestamp(end_timestamp, tz="Asia/Shanghai").start_of('day')
    return (end_date - start_date).in_days()

# Notion 其他工具函数
upload_url = "https://wereadassets.malinkang.com/"  # 图片上传图床，由malinkang维护


def upload_image(folder_path, filename, file_path):
    """
    上传图片
    :param folder_path: 文件夹路径
    :param filename: 文件名
    :param file_path: 文件路径
    :return: 上传成功返回图片链接，失败返回None
    """
    # 将文件内容编码为Base64
    with open(file_path, "rb") as file:
        content_base64 = base64.b64encode(file.read()).decode("utf-8")

    # 构建请求的JSON数据
    data = {"file": content_base64, "filename": filename, "folder": folder_path}

    response = requests.post(upload_url, json=data)

    if response.status_code == 200:
        print("File uploaded successfully.")
        return response.text
    else:
        return None

def download_image(url, save_dir="cover"):
    """
    下载图片
    :param url: 图片URL
    :param save_dir: 保存目录
    :return: 保存路径
    """
    # 确保目录存在，如果不存在则创建
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    file_name = url_to_md5(url) + ".jpg"
    save_path = os.path.join(save_dir, file_name)

    # 检查文件是否已经存在，如果存在则不进行下载
    if os.path.exists(save_path):
        print(f"File {file_name} already exists. Skipping download.")
        return save_path

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=128):
                file.write(chunk)
        print(f"Image downloaded successfully to {save_path}")
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
    return save_path

def url_to_md5(url):
    """
    将URL转换为MD5
    :param url: URL
    :return: MD5
    """
    # 创建一个md5哈希对象
    md5_hash = hashlib.md5()

    # 对URL进行编码，准备进行哈希处理
    # 默认使用utf-8编码
    encoded_url = url.encode("utf-8")

    # 更新哈希对象的状态
    md5_hash.update(encoded_url)

    # 获取十六进制的哈希表示
    hex_digest = md5_hash.hexdigest()

    return hex_digest
