import os
import time
import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from datetime import datetime, timedelta
from urllib.parse import urljoin

# 1. 获取环境变量
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY")
DOUBAO_ENDPOINT = os.environ.get("DOUBAO_ENDPOINT")

# 2. 纯净版 RSS 列表 (使用稳定的正式订阅源)
RSS_FEEDS = [
    "https://pubsonline.informs.org/action/showFeed?type=etoc&feed=rss&jc=mksc",
    "https://pubsonline.informs.org/action/showFeed?type=etoc&feed=rss&jc=mnsc",
    "https://pubsonline.informs.org/action/showFeed?type=etoc&feed=rss&jc=isre",
    "https://pubsonline.informs.org/action/showFeed?type=etoc&feed=rss&jc=msom",
    "https://journals.sagepub.com/action/showFeed?jc=jmxa&type=etoc&feed=rss",
    "https://journals.sagepub.com/action/showFeed?jc=mrja&type=etoc&feed=rss",
    "https://journals.sagepub.com/action/showFeed?jc=jnma&type=etoc&feed=rss",
    "https://onlinelibrary.wiley.com/feed/10970266/most-recent",
    "https://onlinelibrary.wiley.com/feed/15405885/most-recent",
    "https://link.springer.com/search.rss?facet-journal-id=41267&facet-content-type=Article",
    "https://link.springer.com/search.rss?facet-journal-id=11002&facet-content-type=Article",
    "https://rss.sciencedirect.com/publication/science/03043878",
    "https://rss.sciencedirect.com/publication/science/01678116",
    "https://rss.sciencedirect.com/publication/science/00224359",
    "https://consumerresearcher.com/feed" 
]

def discover_rss(url):
    """尝试从网页 Homepage 中自动发现 RSS 链接"""
    if url.endswith('.xml') or url.endswith('.rss') or 'feed' in url:
        return url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        link_tag = soup.find('link', type='application/rss+xml') or soup.find('link', type='application/atom+xml')
        if link_tag and link_tag.get('href'):
            rss_url = link_tag.get('href')
            if rss_url.startswith('/'):
                rss_url = urljoin(url, rss_url)
            return rss_url
    except Exception as e:
        pass
    return url 

def fetch_recent_papers():
    paper_list_data = ""
    # 【改动】放宽到 30 天，有效防止漏掉几天前刚更新的优秀文章
    thirty_days_ago_ts = time.time() - (30 * 24 * 60 * 60)
    
    for homepage_url in RSS_FEEDS:
        print(f"正在探测: {homepage_url}")
        actual_rss_url = discover_rss(homepage_url)
        
        try:
            feed = feedparser.parse(actual_rss_url)
            valid_entries = 0
            journal_name = feed.feed.get('title', '未知期刊')
            
            for entry in feed.entries:
                entry_ts = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    entry_ts = time.mktime(entry.published_parsed)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    entry_ts = time.mktime(entry.updated_parsed)
                
                # 如果时间戳在 30 天内，或者压根没写时间（有些期刊比较随意），都抓取
                if entry_ts is None or entry_ts >= thirty_days_ago_ts:
                    title = entry.title
                    author = entry.get('author', '未知作者')
                    published = entry.get('published', '未知时间')
                    summary = entry.get('summary', '无摘要')
                    link = entry.link
                    
                    paper_list_data += f"【期刊】{journal_name}\n【标题】{title}\n【作者】{author}\n【时间】{published}\n【摘要】{summary}\n【链接】{link}\n\n"
                    valid_entries += 1
            
            print(f"-> 获取到 {valid_entries} 篇近 30 天的文章。")
        except Exception as e:
            print(f"抓取失败: {e}")
            continue
            
    return paper_list_data

def summarize_with_doubao(text):
    if not text.strip():
        return "近期暂未获取到新的论文更新哦。"
    
    client = OpenAI(
    api_key=DOUBAO_API_KEY,
    base_url="https://api.deepseek.com",
    )
    
    prompt = f"""
    你是一个顶级的科研助手。以下是近期各大顶会/期刊新发表的论文数据。
    请你对这些论文进行通读筛选，并**生成一份精美的 Markdown 科研周报**。
    
    【格式严格要求】
    对于你筛选出最有价值的论文（如果数量太多，请精选最重要的10-15篇），必须严格按照以下顺序的6个段落进行排版（千万不要乱排）：
    
    **📖 期刊名称**：[填写英文期刊名称]
    **📄 文章标题**：
    [填写英文原标题]
    [填写中文翻译标题]
    **👤 作者**：[填写原作者信息]
    **📅 发表时间**：[填写提取出的日期]
    **🔗 网址链接**：[填写原文链接地址]
    **💡 Abstract 总结**：
    [这里先写一段英文摘要总结，用英文精炼概括核心内容，约50个单词]
    [这里再写一段中文摘要总结，用中文精炼概括核心创新点、研究方法和结论，约150个中文字]
    
    ---
    （不同论文之间用分隔线隔开）
    
    请直接输出排版好的正文，不要有任何多余的寒暄。
    
    【论文原始数据】
    {text}
    """
    
    try:
        response = client.chat.completions.create(
            model=DOUBAO_ENDPOINT, 
            messages=[
                {"role": "system", "content": "你是一个严谨客观的科研助手，精通严格按照指定格式输出 Markdown 文档。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"豆包总结失败，错误信息: {e}"

def send_to_feishu_card(markdown_text):
    headers = {"Content-Type": "application/json"}
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "📚 专属科研周报 (严选版)"
                }
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": markdown_text
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "🤖 由自动化 Agent 抓取并由豆包模型生成精选摘要"
                        }
                    ]
                }
            ]
        }
    }
    requests.post(FEISHU_WEBHOOK, json=payload, headers=headers)

if __name__ == "__main__":
    print("开始扫描期刊并抓取论文...")
    papers = fetch_recent_papers()
    
    if papers.strip():
        print("正在请求豆包 API 进行深入总结并生成 Markdown...")
        summary = summarize_with_doubao(papers)
        print("正在发送到飞书...")
        send_to_feishu_card(summary)
    else:
        print("没有抓取到近期文章。")
        send_to_feishu_card("近期暂无相关期刊文章更新。")
        
    print("全部任务完成！")
