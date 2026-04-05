# -*- coding: utf-8 -*-
# Notion API核心操作，包括数据库查询、页面创建和更新等功能的封装，以及一些工具函数
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

from notion_client import Client
import pendulum
from retrying import retry
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()
from .notion_builders import (
    format_date,
    get_date,
    get_first_and_last_day_of_month,
    get_first_and_last_day_of_week,
    get_first_and_last_day_of_year,
    get_icon,
    get_number,
    get_relation,
    get_rich_text,
    get_title,
    timestamp_to_date,
    get_property_value,
)

TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TARGET_ICON_URL = "https://www.notion.so/icons/target_red.svg"
BOOKMARK_ICON_URL = "https://www.notion.so/icons/bookmark_gray.svg"

class NotionHelper:
    _DB_NAME_DICT = {
        "BOOK_DATABASE_NAME": "书架",
        "REVIEW_DATABASE_NAME": "笔记",
        "BOOKMARK_DATABASE_NAME": "划线",
        "DAY_DATABASE_NAME": "日",
        "WEEK_DATABASE_NAME": "周",
        "MONTH_DATABASE_NAME": "月",
        "YEAR_DATABASE_NAME": "年",
        "CATEGORY_DATABASE_NAME": "分类",
        "AUTHOR_DATABASE_NAME": "作者",
        "CHAPTER_DATABASE_NAME": "章节",
        "READ_DATABASE_NAME": "阅读记录",
        "SETTING_DATABASE_NAME": "设置",
    }
    database_id_dict = {}
    heatmap_block_id = None
    show_color = True
    block_type = "callout"
    sync_bookmark = True

    # 初始化与配置
    def __init__(self):
        self.client = Client(auth=os.getenv("NOTION_TOKEN"), log_level=logging.ERROR)
        self.cache = {}
        self.page_id = self.extract_page_id(os.getenv("NOTION_PAGE"))
        self.search_database(self.page_id)
        self.database_name_dict = self._DB_NAME_DICT.copy()
        # 环境变量中若设置了某数据库的名称，则使用自定义名称
        for key in self.database_name_dict.keys():
            if os.getenv(key) != None and os.getenv(key) != "":
                self.database_name_dict[key] = os.getenv(key)
        for key in self.database_name_dict.keys():
            attr_name = key.replace("_DATABASE_NAME", "_database_id").lower()
            db_name = self.database_name_dict.get(key)
            setattr(self, attr_name, self.database_id_dict.get(db_name))
        self.update_book_database()
        if self.read_database_id is None:
            self.create_read_database()
        if self.setting_database_id is None:
            self.create_setting_database()
        if self.setting_database_id:
            self.insert_to_setting_database()
    def extract_page_id(self, notion_url):
        """
        获取Notion页面ID的函数，支持从完整的URL中提取ID
        :param notion_url: Notion页面的完整URL
        :return: Notion页面ID
        """
        match = re.search(
            r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
            notion_url,
        )
        if match:
            return match.group(0)
        else:
            raise Exception(f"获取NotionID失败，请检查输入的Url是否正确")
        
    def search_database(self, block_id):
        """
        搜索数据库，递归搜索页面下所有子数据库和热力图 block
        :param block_id: Notion块ID
        """
        children = self.client.blocks.children.list(block_id=block_id)["results"]
        # 遍历子块
        for child in children:
            # 检查子块的类型
            if child["type"] == "child_database":
                self.database_id_dict[child.get("child_database").get("title")] = (
                    child.get("id")
                )
            elif child["type"] == "embed" and child.get("embed").get("url"):
                if child.get("embed").get("url").startswith("https://heatmap.malinkang.com/"):
                    self.heatmap_block_id = child.get("id")
            # 如果子块有子块，递归调用函数
            if "has_children" in child and child["has_children"]:
                self.search_database(child["id"])

    # 数据库结构管理函数
    def update_book_database(self):
        """
        更新数据库
        :return: None
        """
        try:
            response = self.client.databases.retrieve(database_id=self.book_database_id)
        except Exception as e:
            logger.error(f"获取数据库信息失败: {e}")
            return
            
        id = response.get("id")
        properties = response.get("properties")
        
        if not properties:
            logger.warning(f"数据库 properties 为空，跳过更新")
            return
            
        update_properties = {}
        if (
            properties.get("阅读时长") is None
            or properties.get("阅读时长").get("type") != "number"
        ):
            update_properties["阅读时长"] = {"number": {}}
        if (
            properties.get("书架分类") is None
            or properties.get("书架分类").get("type") != "select"
        ):
            update_properties["书架分类"] = {"select": {}}
        if (
            properties.get("豆瓣链接") is None
            or properties.get("豆瓣链接").get("type") != "url"
        ):
            update_properties["豆瓣链接"] = {"url": {}}
        if (
            properties.get("我的评分") is None
            or properties.get("我的评分").get("type") != "select"
        ):
            update_properties["我的评分"] = {"select": {}}
        if (
            properties.get("豆瓣短评") is None
            or properties.get("豆瓣短评").get("type") != "rich_text"
        ):
            update_properties["豆瓣短评"] = {"rich_text": {}}
        if len(update_properties) > 0:
            self.client.databases.update(database_id=id, properties=update_properties)

    def create_read_database(self):
        """
        创建阅读记录数据库
        :return: None
        """
        title = [
            {
                "type": "text",
                "text": {
                    "content": self.database_name_dict.get("READ_DATABASE_NAME"),
                },
            },
        ]
        properties = {
            "标题": {"title": {}},
            "时长": {"number": {}},
            "时间戳": {"number": {}},
            "日期": {"date": {}},
            "书架": {
                "relation": {
                    "database_id": self.book_database_id,
                    "single_property": {},
                }
            },
        }
        parent = parent = {"page_id": self.page_id, "type": "page_id"}
        self.read_database_id = self.client.databases.create(
            parent=parent,
            title=title,
            icon=get_icon("https://www.notion.so/icons/target_gray.svg"),
            properties=properties,
        ).get("id")
    
    def create_setting_database(self):
        """
        创建设置数据库
        :return: None
        """
        title = [
            {
                "type": "text",
                "text": {
                    "content": self.database_name_dict.get("SETTING_DATABASE_NAME"),
                },
            },
        ]
        properties = {
            "标题": {"title": {}},
            "NotinToken": {"rich_text": {}},
            "NotinPage": {"rich_text": {}},
            "WeReadCookie": {"rich_text": {}},
            "根据划线颜色设置文字颜色": {"checkbox": {}},
            "同步书签": {"checkbox": {}},
            "样式": {
                "select": {
                    "options": [
                        {"name": "callout", "color": "blue"},
                        {"name": "quote", "color": "green"},
                        {"name": "paragraph", "color": "purple"},
                        {"name": "bulleted_list_item", "color": "yellow"},
                        {"name": "numbered_list_item", "color": "pink"},
                    ]
                }
            },
            "最后同步时间": {"date": {}},
        }
        parent = parent = {"page_id": self.page_id, "type": "page_id"}
        self.setting_database_id = self.client.databases.create(
            parent=parent,
            title=title,
            icon=get_icon("https://www.notion.so/icons/gear_gray.svg"),
            properties=properties,
        ).get("id")

    # 设置同步
    def insert_to_setting_database(self):
        """
        将运行配置同步到设置数据库，同时读取用户的样式配置
        :return: None
        """
        existing_pages = self.query(database_id=self.setting_database_id, filter={"property": "标题", "title": {"equals": "设置"}}).get("results")
        properties = {
            "标题": {"title": [{"type": "text", "text": {"content": "设置"}}]},
            "最后同步时间": {"date": {"start": pendulum.now("Asia/Shanghai").isoformat()}},
            "NotinToken": {"rich_text": [{"type": "text", "text": {"content": os.getenv("NOTION_TOKEN")}}]},
            "NotinPage": {"rich_text": [{"type": "text", "text": {"content": os.getenv("NOTION_PAGE")}}]},
            "WeReadCookie": {"rich_text": [{"type": "text", "text": {"content": os.getenv("WEREAD_COOKIE")}}]},
        }
        if existing_pages:
            remote_properties = existing_pages[0].get("properties")
            self.show_color = get_property_value(remote_properties.get("根据划线颜色设置文字颜色"))
            self.sync_bookmark = get_property_value(remote_properties.get("同步书签"))
            self.block_type = get_property_value(remote_properties.get("样式"))
            page_id = existing_pages[0].get("id")
            self.client.pages.update(page_id=page_id, properties=properties)
        else:
            properties["根据划线颜色设置文字颜色"] = {"checkbox": True}
            properties["同步书签"] = {"checkbox": True}
            properties["样式"] = {"select": {"name": "callout"}}
            self.client.pages.create(
                parent={"database_id": self.setting_database_id},
                properties=properties,
            )

    # 时间维度关系管理
    def get_week_relation_id(self, date):
        """
        获取给定日期所在周的 id
        :param date: date
        :return: id
        """
        year = date.isocalendar().year
        week = date.isocalendar().week
        week = f"{year}年第{week}周"
        start, end = get_first_and_last_day_of_week(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            week, self.week_database_id, TARGET_ICON_URL, properties
        )

    def get_month_relation_id(self, date):
        """
        获取给定日期所在月的 id
        :param date: date
        :return: id
        """
        month = date.strftime("%Y年%-m月")
        start, end = get_first_and_last_day_of_month(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            month, self.month_database_id, TARGET_ICON_URL, properties
        )

    def get_year_relation_id(self, date):
        """
        获取给定日期所在年的 id
        :param date: date
        :return: id
        """
        year = date.strftime("%Y")
        start, end = get_first_and_last_day_of_year(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            year, self.year_database_id, TARGET_ICON_URL, properties
        )

    def get_day_relation_id(self, date):
        """
        获取给定日期的 id
        :param date: date
        :return: id
        """
        new_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        timestamp = (new_date - timedelta(hours=8)).timestamp()
        day = new_date.strftime("%Y年%m月%d日")
        properties = {
            "日期": get_date(format_date(date)),
            "时间戳": get_number(timestamp),
        }
        properties["年"] = get_relation(
            [
                self.get_year_relation_id(new_date),
            ]
        )
        properties["月"] = get_relation(
            [
                self.get_month_relation_id(new_date),
            ]
        )
        properties["周"] = get_relation(
            [
                self.get_week_relation_id(new_date),
            ]
        )
        return self.get_relation_id(
            day, self.day_database_id, TARGET_ICON_URL, properties
        )

    def get_relation_id(self, name, id, icon, properties={}):
        """
        获取指定名称的 id
        :param name: 名称
        :param id: 数据库 id
        :param icon: 图标 url
        :param properties: 属性
        :return: id
        """
        key = f"{id}{name}"
        if key in self.cache:
            return self.cache.get(key)
        filter = {"property": "标题", "title": {"equals": name}}
        response = self.client.databases.query(database_id=id, filter=filter)
        if len(response.get("results")) == 0:
            parent = {"database_id": id, "type": "database_id"}
            properties["标题"] = get_title(name)
            page_id = self.client.pages.create(
                parent=parent, properties=properties, icon=get_icon(icon)
            ).get("id")
        else:
            page_id = response.get("results")[0].get("id")
        self.cache[key] = page_id
        return page_id

    def get_date_relation(self, properties, date):
        """
        批量设置年月周日关系属性
        :param properties: 属性
        :param date: 日期
        :return: None
        """
        properties["年"] = get_relation(
            [
                self.get_year_relation_id(date),
            ]
        )
        properties["月"] = get_relation(
            [
                self.get_month_relation_id(date),
            ]
        )
        properties["周"] = get_relation(
            [
                self.get_week_relation_id(date),
            ]
        )
        properties["日"] = get_relation(
            [
                self.get_day_relation_id(date),
            ]
        )

    # 数据插入
    def insert_bookmark(self, id, bookmark):
        """
        插入划线到“书签”数据库
        :param id: 书籍 id
        :param bookmark: 书签
        :return: None
        """
        icon = get_icon(BOOKMARK_ICON_URL)
        properties = {
            "Name": get_title(bookmark.get("markText", "")),
            "bookId": get_rich_text(bookmark.get("bookId")),
            "range": get_rich_text(bookmark.get("range")),
            "bookmarkId": get_rich_text(bookmark.get("bookmarkId")),
            "blockId": get_rich_text(bookmark.get("blockId")),
            "chapterUid": get_number(bookmark.get("chapterUid")),
            "bookVersion": get_number(bookmark.get("bookVersion")),
            "colorStyle": get_number(bookmark.get("colorStyle")),
            "type": get_number(bookmark.get("type")),
            "style": get_number(bookmark.get("style")),
            "书籍": get_relation([id]),
        }
        if "createTime" in bookmark:
            create_time = timestamp_to_date(int(bookmark.get("createTime")))
            properties["Date"] = get_date(create_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.get_date_relation(properties, create_time)
        parent = {"database_id": self.bookmark_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    def insert_review(self, id, review):
        """
        插入笔记到“笔记”数据库
        :param id: 书籍 id
        :param review: 笔记
        :return: None
        """
        time.sleep(0.1)
        icon = get_icon(TAG_ICON_URL)
        properties = {
            "Name": get_title(review.get("content", "")),
            "bookId": get_rich_text(review.get("bookId")),
            "reviewId": get_rich_text(review.get("reviewId")),
            "blockId": get_rich_text(review.get("blockId")),
            "chapterUid": get_number(review.get("chapterUid")),
            "bookVersion": get_number(review.get("bookVersion")),
            "type": get_number(review.get("type")),
            "书籍": get_relation([id]),
        }
        if "range" in review:
            properties["range"] = get_rich_text(review.get("range"))
        if "star" in review:
            properties["star"] = get_number(review.get("star"))
        if "abstract" in review:
            properties["abstract"] = get_rich_text(review.get("abstract"))
        if "createTime" in review:
            create_time = timestamp_to_date(int(review.get("createTime")))
            properties["Date"] = get_date(create_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.get_date_relation(properties, create_time)
        parent = {"database_id": self.review_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    def insert_chapter(self, id, chapter):
        """
        插入章节到“章节”数据库
        :param id: 书籍 id
        :param chapter: 章节
        :return: None
        """
        time.sleep(0.1)
        icon = {"type": "external", "external": {"url": TAG_ICON_URL}}
        properties = {
            "Name": get_title(chapter.get("title")),
            "blockId": get_rich_text(chapter.get("blockId")),
            "chapterUid": {"number": chapter.get("chapterUid")},
            "chapterIdx": {"number": chapter.get("chapterIdx")},
            "readAhead": {"number": chapter.get("readAhead")},
            "updateTime": {"number": chapter.get("updateTime")},
            "level": {"number": chapter.get("level")},
            "书籍": {"relation": [{"id": id}]},
        }
        parent = {"database_id": self.chapter_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    # 页面操作
    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_book_page(self, page_id, properties):
        """
        更新书籍页面属性
        :param page_id: 页面 id
        :param properties: 属性
        :return: 更新结果
        """
        return self.client.pages.update(page_id=page_id, properties=properties)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_page(self, page_id, properties, cover, icon=None):
        """
        更新页面属性
        :param page_id: 页面 id
        :param properties: 属性
        :param cover: 封面
        :param icon: 图标
        :return: 更新结果
        """
        return self.client.pages.update(
            page_id=page_id, properties=properties, cover=cover, icon=icon
        )


    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_page(self, parent, properties, icon):
        """
        创建页面
        :param parent: 父级数据库
        :param properties: 属性
        :param icon: 图标
        :return: 创建结果
        """
        return self.client.pages.create(parent=parent, properties=properties, icon=icon)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_book_page(self, parent, properties, icon):
        """
        创建书籍页面
        :param parent: 父级数据库
        :param properties: 属性
        :param icon: 图标
        :return: 创建结果
        """
        return self.client.pages.create(
            parent=parent, properties=properties, icon=icon, cover=icon
        )

    # 查询操作
    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query(self, **kwargs):
        """
        查询数据库
        :param kwargs: 查询参数
        :return: 查询结果
        """

        kwargs = {k: v for k, v in kwargs.items() if v}
        return self.client.databases.query(**kwargs)
    
    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_all_book(self):
        """
        从Notion中获取所有的书籍
        :return: 所有书籍
        """
        results = self.query_all(self.book_database_id)
        books_dict = {}
        for result in results:
            bookId = get_property_value(result.get("properties").get("BookId"))
            books_dict[bookId] = {
                "pageId": result.get("id"),
                "readingTime": get_property_value(
                    result.get("properties").get("阅读时长")
                ),
                "category": get_property_value(
                    result.get("properties").get("书架分类")
                ),
                "Sort": get_property_value(result.get("properties").get("Sort")),
                "douban_url": get_property_value(
                    result.get("properties").get("豆瓣链接")
                ),
                "cover": result.get("cover"),
                "myRating": get_property_value(
                    result.get("properties").get("我的评分")
                ),
                "comment": get_property_value(result.get("properties").get("豆瓣短评")),
                "status": get_property_value(result.get("properties").get("阅读状态")),
            }
        return books_dict

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all_by_book(self, database_id, filter):
        """
        查询数据库
        :param database_id: 数据库id
        :param filter: 查询条件
        :return: 查询结果
        """
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                filter=filter,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all(self, database_id):
        """
        获取database中所有的数据
        :param database_id: 数据库id
        :return: 数据库所有数据
        """
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results

    # 块操作
    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_block_children(self, id):
        """
        获取块的子块
        :param id: 块id
        :return: 子块
        """
        response = self.client.blocks.children.list(id)
        return response.get("results")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks(self, block_id, children):
        """
        在块后面添加子块
        :param block_id: 块id
        :param children: 子块
        :return: None
        """
        return self.client.blocks.children.append(block_id=block_id, children=children)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks_after(self, block_id, children, after):
        """
        在指定位置后面添加子块
        :param block_id: 块id
        :param children: 子块
        :param after: 指定位置
        :return: None
        """
        parent = self.client.blocks.retrieve(after).get("parent")
        if(parent.get("type")=="block_id"):
            after = parent.get("block_id")
        return self.client.blocks.children.append(
            block_id=block_id, children=children, after=after
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def delete_block(self, block_id):
        """
        删除块
        :param block_id: 块id
        :return: None
        """
        return self.client.blocks.delete(block_id=block_id)
    
    # 热力图相关函数
    def update_heatmap(self, block_id, url):
        """
        更新热力图块的链接
        :param block_id: 热力图 block 的 id
        :param url: 热力图图片的 url
        :return: None
        """
        return self.client.blocks.update(block_id=block_id, embed={"url": url})
