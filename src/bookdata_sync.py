import pendulum
from .notion_func.notion_helper import NotionHelper
from .notion_func import notion_builders
from .weread_func.weread_api import WeReadAPI
from .notion_func.notion_db_prop_config import book_properties_type_dict, tz

TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
BOOK_ICON_URL = "https://www.notion.so/icons/book_gray.svg"
rating = {"poor": "⭐️", "fair": "⭐️⭐️⭐️", "good": "⭐️⭐️⭐️⭐️⭐️"}

def build_shelf_cache(bookshelf):
    """
    将书架数据转换为以 bookId 为键的字典
    :param bookshelf: 书架数据
    :return: {bookId: book_data}
    """
    cache = {}
    for book in bookshelf:
        if "bookId" not in book:
            continue
        book_id = book.get("bookId")
        if book_id in cache:
            continue
        cache[book_id] = {
            "bookId": book_id,
            "title": book.get("title"),
            "author": book.get("author"),
            "cover": book.get("cover"),
            "categories": book.get("categories", []),
            "newRating": book.get("newRating"),
            "newRatingDetail": book.get("newRatingDetail"),
            "price": book.get("price"),
            "totalWords": book.get("totalWords"),
            "lastChapterIdx": book.get("lastChapterIdx"),
            "finishReading": book.get("finishReading"),     # 0=未读完, 1=已读完
            "readUpdateTime": book.get("readUpdateTime"),
            "updateTime": book.get("updateTime"),           # 加入书架的时间
            "_from_shelf": True,                            # 标记来源
        }
    return cache

def merge_shelf_and_notebook(shelf_cache, notebook_list):
    """
    将书架数据与笔记数据进行合并
    :param shelf_cache: 书架数据
    :param notebook_list: 笔记数据
    :return: 合并后的数据
    """
    merged = shelf_cache.copy()

    for nb in notebook_list:
        book_id = nb.get("bookId")
        if not book_id:
            continue
        book_data = nb.get("book")
        if book_id in merged:
            merged[book_id]["noteCount"] = nb.get("noteCount", 0)  
            merged[book_id]["reviewCount"] = nb.get("reviewCount", 0)
            merged[book_id]["bookmarkCount"] = nb.get("bookmarkCount", 0)
            merged[book_id]["sort"] = nb.get("sort", 0)
        else:
            merged[book_id] = {
                "bookId": book_id,
                "title": book_data.get("title"),
                "author": book_data.get("author"),
                "cover": book_data.get("cover"),
                "isbn": book_data.get("isbn"),
                "intro": book_data.get("intro"),
                "categories": book_data.get("categories", []),
                "newRating": book_data.get("newRating"),
                "newRatingDetail": book_data.get("newRatingDetail"),
                "price": book_data.get("price"),
                "totalWords": book_data.get("totalWords", 0),        # 没有这字段
                "lastChapterIdx": book_data.get("lastChapterIdx"),
                "finishReading": book_data.get("finishReading", 0),     # 0=未读完, 1=已读完
                "readUpdateTime": book_data.get("readUpdateTime", 0),
                "updateTime": book_data.get("updateTime", 0),           # 加入书架的时间
                "noteCount": nb.get("noteCount", 0),  
                "reviewCount": nb.get("reviewCount", 0),
                "bookmarkCount": nb.get("bookmarkCount", 0),
                "sort": nb.get("sort", 0),
                "_from_notebook": True,  # 标记来源
            }
    return merged

def parse_read_info(read_info):
    """
    解析阅读进度信息，统一字段名
    """
    if not read_info:
        return {}
    
    extracted = {}
    read_book_id = read_info.get("bookId")
    if not read_book_id:
        return {}
    read_book_data = read_info.get("book", {})
    readingTime = read_book_data.get("readingTime")
    readingProgress = read_book_data.get("progress")
    finishTime = read_book_data.get("finishTime")
    isStartReading = read_book_data.get("isStartReading", 0)
    startReadingTime = read_book_data.get("startReadingTime")
    updateTime = read_book_data.get("updateTime")
    if finishTime:
        markedStatus = 4   # 已读完
        totalReadDay = notion_builders.get_days_between(startReadingTime, finishTime) if startReadingTime and finishTime else 0
    elif readingTime and isStartReading:
        markedStatus = 2   # 在读
        totalReadDay = notion_builders.get_days_between(startReadingTime, updateTime) if startReadingTime and updateTime else 0
    else:
        markedStatus = 1   # 想读
        totalReadDay = 0

    extracted = {
        "readingTime": readingTime,
        "readingProgress": readingProgress,
        "markedStatus": markedStatus,
        "totalReadDay": totalReadDay,
        "startReadingTime": startReadingTime,
        "updateTime": updateTime,
        "finishedDate": finishTime,
        "summary": read_book_data.get("summary") or None,
    }
    return extracted

def should_sync_book(notion_book, read_info):
    """
    判断书籍是否需要同步
    :param notion_book: Notion 中的书籍
    :param read_info: 阅读信息
    :return (should_sync, reason): 是否需要同步, 原因
    """
    if notion_book is None:
        return True, "新书"
    if not read_info:
        return False, "无阅读信息"
    # 检查阅读时间是否变化
    old_time = notion_book.get("readingTime") or 0
    new_time = read_info.get("readingTime") or 0
    
    if new_time > old_time:
        return True, f"阅读时间变化 ({old_time} -> {new_time})"
    
    # 检查阅读进度是否变化。
    old_progress = (notion_book.get("阅读进度") or 0) * 100
    new_progress = read_info.get("readingProgress") or 0
    
    if abs(new_progress - old_progress) > 1:  # 进度变化超过 1%
        return True, f"阅读进度变化 ({old_progress:.1f}% -> {new_progress:.1f}%)"
    
    # 检查笔记数量是否变化（如果有笔记数据）
    old_note_count = notion_book.get("noteCount", 0)
    new_note_count = read_info.get("noteCount") or 0
    if old_note_count != new_note_count:
        return True, f"笔记数量变化 ({old_note_count} -> {new_note_count})"
    
    # 检查划线数量是否变化（如果有划线数据）
    old_bookmark_count = notion_book.get("bookmarkCount", 0)
    new_bookmark_count = read_info.get("bookmarkCount", 0)
    if old_bookmark_count != new_bookmark_count:
        return True, f"划线数量变化 ({old_bookmark_count} -> {new_bookmark_count})"

    return False, "无需更新"

def prepare_book_data(shelf_book, read_info, archive_name=None):
    """
    准备书籍数据，合并书架信息和阅读信息
    :param shelf_book: 书架中的书籍数据
    :param read_info: 阅读信息
    :param archive_name: 书架分类名称（如果有）
    :return: 准备好的书籍数据字典
    """
    merge_book = {**shelf_book, **read_info}
    
    # 添加书架分类
    if archive_name:
        merge_book["书架分类"] = archive_name
    
    # 计算阅读状态
    marked_status = merge_book.get("markedStatus", 1)
    if marked_status == 4:
        status = "已读"
    elif marked_status == 2:
        status = "在读"
    else:
        status = "想读"
    merge_book["阅读状态"] = status
    
    # 计算阅读进度（转换为 0-1 的小数）
    merge_book["阅读进度"] = (merge_book.get("readingProgress") or 0) / 100
    
    # 处理封面链接
    cover = (merge_book.get("cover") or "").replace("/s_", "/t7_")
    if not cover or not cover.strip() or not cover.startswith("http"):
        cover = BOOK_ICON_URL
    merge_book["封面"] = cover
    
    # 处理评分
    merge_book["评分"] = merge_book.get("newRating")
    newRatingDetail = merge_book.get("newRatingDetail", {})
    myRating = newRatingDetail.get("myRating") if newRatingDetail else None
    if myRating:
        merge_book["我的评分"] = rating.get(myRating, myRating)
    else:
        merge_book["我的评分"] = "未评分"
    
    # 处理阅读时间日期（避免 0 值导致写入 1970-01-01）
    start_time = merge_book.get("startReadingTime")
    if start_time:
        merge_book["开始阅读时间"] = start_time
    
    update_time = merge_book.get("updateTime")
    if update_time:
        merge_book["最后阅读时间"] = update_time
    
    finished_time = merge_book.get("finishedDate")
    if finished_time:
        merge_book["时间"] = finished_time
    
    merge_book["阅读天数"] = merge_book.get("totalReadDay", 0)
    merge_book["阅读时长"] = merge_book.get("readingTime", 0)  # 保持秒为单位，与判断逻辑一致

    return merge_book

def create_book_page(book_id, book_data, notion_helper, weread_api):
    """
    创建 Notion 页面
    :param book_id: 书籍 ID
    :param book_data: 书籍数据
    :param notion_helper: NotionHelper 实例
    :param weread_api: WeReadAPI 实例
    :return: 创建的页面 ID
    """
    property = {
        "书名": notion_builders.get_title(book_data.get("title")),
        "BookId": notion_builders.get_rich_text(book_id),
        "ISBN": notion_builders.get_rich_text(book_data.get("isbn", "")),
        "链接": notion_builders.get_url(weread_api.get_url(book_id)),
        "Sort": notion_builders.get_number(book_data.get("sort", 0)),
        "评分": notion_builders.get_number(book_data.get("newRating", 0)) if book_data.get("newRating") else None,
        "封面": notion_builders.get_file(book_data.get("cover")),
        "阅读状态": notion_builders.get_select(book_data.get("阅读状态")),
        "阅读时长": notion_builders.get_number(book_data.get("阅读时长")) if book_data.get("阅读时长") else None,
        "阅读进度": notion_builders.get_number(book_data.get("阅读进度")) if book_data.get("阅读进度") else None,
        "阅读天数": notion_builders.get_number(book_data.get("阅读天数")) if book_data.get("阅读天数") else None,
        "时间": notion_builders.get_date(book_data.get("时间")) if book_data.get("时间") else None,
        "开始阅读时间": notion_builders.get_date(book_data.get("开始阅读时间")) if book_data.get("开始阅读时间") else None,
        "最后阅读时间": notion_builders.get_date(book_data.get("最后阅读时间")) if book_data.get("最后阅读时间") else None,
        "书架分类": notion_builders.get_select(book_data.get("书架分类")),
        "我的评分": notion_builders.get_select(book_data.get("我的评分")),
        "豆瓣链接": notion_builders.get_url(book_data.get("doubanUrl")),                   
    }

    if book_data.get("intro"):
        property["简介"] = notion_builders.get_rich_text(book_data.get("intro"))
    # 处理作者关系
    if book_data.get("author"):
        author_names = [x.strip() for x in book_data.get("author").split(" ") if x.strip()]
        author_ids = [
            notion_helper.get_relation_id(name, notion_helper.author_database_id, USER_ICON_URL)
            for name in author_names
        ]
        property["作者"] = notion_builders.get_relation(author_ids)
    # 处理分类关系
    if book_data.get("categories"):
        category_ids = [
            notion_helper.get_relation_id(
                cat.get("title"), notion_helper.category_database_id, TAG_ICON_URL
            )
            for cat in book_data.get("categories")
        ]
        property["分类"] = notion_builders.get_relation(category_ids)
    
    # 创建页面
    parent = {"database_id": notion_helper.book_database_id, "type": "database_id"}
    result = notion_helper.create_book_page(
        parent=parent,
        properties=property,
        icon=notion_builders.get_icon(book_data.get("cover")),
    )
    
    return result.get("id")

def update_book_page(book_id, page_id, book_data, notion_helper):
    """
    更新 Notion 页面
    :param book_id: 书籍 ID
    :param page_id: Notion 页面 ID
    :param book_data: 书籍数据
    :param notion_helper: NotionHelper 实例
    """
    property = {
        "评分": notion_builders.get_number(book_data.get("newRating", 0)) if book_data.get("newRating") else None,
        "阅读状态": notion_builders.get_select(book_data.get("阅读状态")),
        "阅读时长": notion_builders.get_number(book_data.get("阅读时长")) if book_data.get("阅读时长") else None,
        "阅读进度": notion_builders.get_number(book_data.get("阅读进度")) if book_data.get("阅读进度") else None,
        "阅读天数": notion_builders.get_number(book_data.get("阅读天数")) if book_data.get("阅读天数") else None,
        "时间": notion_builders.get_date(book_data.get("时间")) if book_data.get("时间") else None,
        "开始阅读时间": notion_builders.get_date(book_data.get("开始阅读时间")) if book_data.get("开始阅读时间") else None,
        "最后阅读时间": notion_builders.get_date(book_data.get("最后阅读时间")) if book_data.get("最后阅读时间") else None,
        "书架分类": notion_builders.get_select(book_data.get("书架分类")),
        "我的评分": notion_builders.get_select(book_data.get("我的评分")),
    }
    
    # 更新页面
    result = notion_helper.update_page(
        page_id=page_id,
        properties=property,
        cover=notion_builders.get_icon(book_data.get("cover")),
        icon=notion_builders.get_icon(book_data.get("cover")),
    )
    
    return result.get("id")
    

def main():
    # 初始化 API 客户端
    weread_api = WeReadAPI()
    notion_helper = NotionHelper()
    
    print("=" * 50)
    print("微信读书书架同步")
    print("=" * 50)
    
    # 1. 获取书架和笔记本数据
    print("\n[1/4] 获取书架数据...")
    bookshelf = weread_api.get_bookshelf()
    shelf_cache = build_shelf_cache(bookshelf)
    print(f"  ✓ 书架书籍: {len(shelf_cache)} 本")
    shelf_cache_top5 = {}
    # 取书架书籍的前5本: TODO
    for k, v in shelf_cache.items():
        shelf_cache_top5[k] = v
        print(f"[{k}] raw book data: {v}")
        if len(shelf_cache_top5) >= 5:
            break
    
    print("\n[2/4] 获取笔记本数据...")
    notebook_list = weread_api.get_notebooklist()
    print(f"  ✓ 笔记本书籍: {len(notebook_list)} 本")
    # 取笔记本书籍的前5本
    notebook_list_top5 = notebook_list[:5]
    
    # 合并数据
    all_books = merge_shelf_and_notebook(shelf_cache_top5, notebook_list_top5)
    print(f"  ✓ 合并后书籍: {len(all_books)} 本")
    
    # 处理书架分类（bookshelf 为 booksAndArchives 列表，archive 项为列表中的对象）
    archive_dict = {}
    for item in bookshelf:
        if item.get("type") == "archive" or "bookIds" in item:
            for book_id in item.get("bookIds", []):
                archive_dict[book_id] = item.get("name")
    print(f"  ✓ 书架分类: {len(set(archive_dict.values()))} 个")
    
    # 2. 获取 Notion 已有书籍
    print("\n[3/4] 获取 Notion 已有书籍...")
    notion_books = notion_helper.get_all_book()
    print(f"  ✓ Notion 书籍: {len(notion_books)} 本")
    
    # 3. 分类处理（使用缓存避免重复 API 调用）
    print("\n[4/4] 检查书籍同步状态...")
    new_books = []
    update_books = []
    skip_books = []
    
    for book_id, book_info in all_books.items():
        # 获取阅读进度
        read_info_raw = weread_api.get_read_info(book_id)
        print(f"[{book_id}]:{read_info_raw}")
        read_info = parse_read_info(read_info_raw)
        print(f"[{book_id}]:解析后的阅读信息: {read_info}")

        notion_book = notion_books.get(book_id)
        should_sync, reason = should_sync_book(notion_book, read_info)
        print(f"  [{book_id}],{should_sync},{reason}")

        if not should_sync:
            skip_books.append((book_id, reason))
            continue
        
        # 准备数据
        archive_name = archive_dict.get(book_id)
        book_data = prepare_book_data(book_info, read_info, archive_name)
        
        if notion_book is None:
            new_books.append((book_id, book_data))
        else:
            print(f"[{book_id}] in Notion:{notion_book}")
            update_books.append((book_id, notion_book.get("pageId"), book_data))
    
    print(f"  ✓ 新书: {len(new_books)} 本")
    print(f"  ✓ 需更新: {len(update_books)} 本")
    print(f"  ✓ 跳过: {len(skip_books)} 本")
    
    # 4. 同步到 Notion
    print("\n" + "-" * 50)
    print("开始同步...")
    
    # 创建新书
    for i, (book_id, book_data) in enumerate(new_books, 1):
        try:
            title = book_data.get("title", "未知书名")
            print(f"  [{i}/{len(new_books)}] 创建《{title}》...", end=" ")
            page_id = create_book_page(book_id, book_data, notion_helper, weread_api)
            print("✓")
        except Exception as e:
            print(f"✗ 错误: {e}")
    
    # 更新已有书
    for i, (book_id, page_id, book_data) in enumerate(update_books, 1):
        try:
            title = book_data.get("title", "未知书名")
            print(f"  [{i}/{len(update_books)}] 更新《{title}》...", end=" ")
            update_book_page(book_id, page_id, book_data, notion_helper)
            print("✓")
        except Exception as e:
            print(f"✗ 错误: {e}")
    
    print("\n" + "=" * 50)
    print("同步完成！")
    print(f"  新建: {len(new_books)} 本")
    print(f"  更新: {len(update_books)} 本")
    print(f"  跳过: {len(skip_books)} 本")
    print("=" * 50)


if __name__ == "__main__":
    main()