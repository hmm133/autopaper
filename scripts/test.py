#!/usr/bin/env python3
"""
从 arXiv 获取 50 篇机器学习相关的论文。
使用 arxiv.py 库，自动处理速率限制和分页。
"""

import arxiv

def main():
    # 创建 arXiv 客户端（使用默认配置，自动遵守 3 秒/请求的限制）
    client = arxiv.Client()

    # 构建搜索请求
    # 查询 "machine learning" 覆盖标题、摘要、作者等字段
    search = arxiv.Search(
        # query = 'machine learning AND submittedDate:[202401010000 TO 202412312359] AND cat:cs.LG',  # 搜索关键词
        query = 'scientific citation',
        max_results=10,                # 总共获取 10 篇论文
        sort_by=arxiv.SortCriterion.SubmittedDate,  # 按提交日期排序（最新优先）
        sort_order=arxiv.SortOrder.Descending
    )

    print(f"正在搜索科学引用相关论文1，最多获取 {search.max_results} 篇...\n")

    # 执行搜索并遍历结果
    try:
        for i, paper in enumerate(client.results(search), start=1):
            print(f"【论文 {i}】")
            print(f"标题：{paper.title}")
            # 作者列表处理
            authors = ", ".join(a.name for a in paper.authors)
            print(f"作者：{authors}")
            print(f"摘要：{paper.summary[:300]}{'...' if len(paper.summary) > 300 else ''}")
            print(f"PDF 链接：{paper.pdf_url}")
            print("-" * 80)
    except Exception as e:
        print(f"获取过程中出现错误：{e}")
        print("请检查网络连接或稍后重试。")

if __name__ == "__main__":
    main()


