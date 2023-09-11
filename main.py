from difflib import SequenceMatcher
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import json

def similarity(text1, text2):
    return SequenceMatcher(None, text1, text2).ratio()

if 'summarized_content' not in st.session_state:
    st.session_state.summarized_content = ""
if 'final_article_content' not in st.session_state:
    st.session_state.final_article_content = ""
if 'prompt' not in st.session_state:
    st.session_state.prompt = ""

API_KEY = st.secrets["api_key"]

# Constants
MAX_RETRY = 10
WAIT_TIME = 5
MAX_ARTICLE_SIZE = 2500

def fetch_from_openai(model, messages, spinner_text):
    with st.spinner(spinner_text):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {API_KEY}',
        }
        data = {
            "model": model,
            'messages': messages,
            'max_tokens': 5000,
            'temperature': 0.2,
        }
        for i in range(MAX_RETRY):
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=data
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            elif response.status_code == 429:
                time.sleep(WAIT_TIME)
            else:
                st.error(f"Error: {response.status_code}, {response.json()}")
                return None
        st.error(f"{MAX_RETRY}번 시도하고 실패함. 잠시 후 다시 해보세요.")
        return None

def crawl_and_get_article(url, index, existing_contents=[]):
    for _ in range(MAX_RETRY):
        r = requests.get(url)
        if r.status_code == 200:
            break
        elif r.status_code == 429:
            time.sleep(WAIT_TIME)
        else:
            st.error(f"Error: {r.status_code}")
            return None

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.select_one('.media_end_head_title')
    title_text = title.get_text(strip=True) if title else f"Title {index} not found"
    article = soup.select_one('article#dic_area')
    article_text = article.get_text(strip=True) if article else f"Article {index} not found"
    article_text = re.sub(r'[\t\r\n]', ' ', article_text)

    if len(article_text) > MAX_ARTICLE_SIZE:
        return None

    # Check for similarity
    for content in existing_contents:
        if similarity(content, article_text) > 0.3:
            return None

    return {"title": title_text, "content": article_text}

# def duplicates(content):
#     response = fetch_from_openai("gpt-4", [
#         {"role": "user",
#          "content": f"{content} 이 리포트에서 내용을 합쳐서 800자에서 1500자 사이로 정리해 줘. 6하 원칙을 모두 살려서 결과를 만들어. 중복된 내용은 최대한 합치고, 중복되지 않은 내용들은 결과물에 모두 나열해 줘. '눈길을 끌었다' '주목된다' 등 판단이나 창의적인 표현들은 빼."}
#     ], "GPT4가 참고용 리포트를 완성하고 있습니다.")
    
#     return response

def main():
    st.title("미디어랩 뉴스봇 프로젝트")

    keyword1 = st.text_input("1번 검색어 : ")
    keyword2 = st.text_input("2번 검색어 : ")
    keyword3 = st.text_input("3번 검색어 : ")

    if st.button("이슈 가져오기"):
        base_url = "https://search.naver.com/search.naver?sm=tab_hty.top&where=news&query="
        search_url = base_url + keyword1 + "+" + keyword2 + "+" + keyword3
        r = requests.get(search_url)
        soup = BeautifulSoup(r.text, "html.parser")
        naver_news_links = [a_tag['href'] for a_tag in soup.select('.info') if '네이버뉴스' in a_tag.text]

        if not naver_news_links:
            st.markdown("<span style='color:red'>검색어를 다시 조정해서 시도해주세요.</span>", unsafe_allow_html=True)
            return

        summarized_content = ""
        crawled_count = 0
        existing_articles = []

        for index, link in enumerate(naver_news_links):
            if crawled_count >= 3:
                break
            crawled_article = crawl_and_get_article(link, index + 1, existing_articles)
            if crawled_article is None:
                continue

            # Append the article to existing_articles list
            existing_articles.append(crawled_article['content'])

            crawled_count += 1
            spinner_text = [
                "첫번째 GPT가 키워드를 정리 하고 있습니다.",
                "두번째 GPT가 줄거리를 정리하고 있습니다.",
                "세번째 GPT가 관련 내용을 모두 담은 리포트를 만드는 중입니다."
            ][crawled_count - 1]
    
            if summarized_content:  
                summarized_content += "\n------\n"  
    
            summarized_content += fetch_from_openai("gpt-4", [
            {"role": "user",
             "content": f"{crawled_article['title']} 및 {crawled_article['content']} 내용들을 문장 구조나 표현 방법 등을 바꿔서 보고서 스타일로 정리해. 누가, 언제, 어디서, 무엇을, 어떻게, 왜 등 6하 원칙을 모두 포함해. 숫자 관련된 내용은 결과물에 전부 포함시키고 절대 틀리지 마. 담을 수 있는 내용 모두를 담아서 전체 1500자 이내로 써 줘. '눈길을 끌었다' '주목된다' 등 판단이나 창의적인 표현들은 빼 줘. 내용 중에 [] 이 대괄호나 = 같은 부호가 들어가지 않게 해줘."}
            ], spinner_text)
        
        # st.session_state.summarized_content = duplicates(summarized_content)
        st.session_state.summarized_content = summarized_content

    if st.session_state.summarized_content:
        st.write("## 참고용 리포트")
    lines = st.session_state.summarized_content.split("\n------\n")
    for i, line in enumerate(lines):
        st.write(line)
        if i < len(lines) - 1:
            st.markdown("<hr/>", unsafe_allow_html=True)

    st.markdown("<span style='color: blue; font-size: large;'>리드문을 아래 필드에 대략 써서 넣으세요.</span>", unsafe_allow_html=True)
    st.session_state.prompt = st.text_area("('6하 원칙'이 포함되면 더 정확한 결과를 만듭니다.)", st.session_state.prompt, height=300)


    if st.button("생성하기"):
        if not st.session_state.summarized_content:
            st.markdown("<span style='color:red'>키워드를 넣고 분석부터 해야 합니다!</span>", unsafe_allow_html=True)
            return 

        if len(st.session_state.prompt) <= 10:
            st.markdown("<span style='color:red'>10자 이상의 리드문을 입력해주세요.</span>", unsafe_allow_html=True)
            return 

        final_article_content = st.session_state.prompt + "\n\n" + st.session_state.summarized_content
        st.session_state.final_article_content = fetch_from_openai("gpt-4", [
            {"role": "user",
             "content": f"이 리포트({st.session_state.summarized_content}) 이 리포트를 토대로 신문 기사를 쓸거야. 정리된 리포트 내용과 조금 다른 문장 구조로 1000자 내로 기사를 써 줘. 특히 숫자와 관련된 내용을 다룰 때 틀리지마. ({st.session_state.prompt})에 써놓은 문장 그대로 기사를 시작해줘. 전체 리포트 중에서 기사 시작문을 중심으로 기사를 써 줘. '~했다' '~됐다'와 같은 반말로 써."}
        ], "GPT4가 리포트를 기사 초안으로 만들고 있습니다.")

    if st.session_state.final_article_content:
        st.write("## 기사 초안")
        st.write(st.session_state.final_article_content)

    if st.session_state.final_article_content:
        st.download_button(
                        label="다운로드",
                        data=st.session_state.final_article_content.encode("utf-8"),
                        file_name="generated_article.txt",
                        mime="text/plain",
                    )

if __name__ == "__main__":
    main()
