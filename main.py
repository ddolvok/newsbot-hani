import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import json

if 'summarized_content' not in st.session_state:
    st.session_state.summarized_content = ""

API_KEY = st.secrets["api_key"]
MAX_RETRY = 10
WAIT_TIME = 5
MAX_ARTICLE_SIZE = 3000  

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

def crawl_and_get_article(url, index):
    crawled_article = {}
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

    crawled_article = {"title": title_text, "content": article_text}

    with open(f'crawled_article_{index}.json', 'w') as f:
        json.dump(crawled_article, f)
    
    return crawled_article

def main():
    st.title("미디어랩 뉴스봇 보고봇 프로젝트")
    
    keyword1 = st.text_input("1번 키워드 : ")
    keyword2 = st.text_input("2번 키워드 : ")
    keyword3 = st.text_input("3번 키워드 : ")
    
    if st.button("이슈 분석하기"):
        base_url = "https://search.naver.com/search.naver?sm=tab_hty.top&where=news&query="
        search_url = base_url + keyword1 + "+" + keyword2 + "+" + keyword3
        r = requests.get(search_url)
        soup = BeautifulSoup(r.text, "html.parser")
        naver_news_links = [a_tag['href'] for a_tag in soup.select('.info') if '네이버뉴스' in a_tag.text]

        if not naver_news_links:
            st.markdown("<span style='color:red'>키워드를 다시 조정해서 시도해주세요.</span>", unsafe_allow_html=True)
            return

        summarized_content = ""

        crawled_count = 0  
        for index, link in enumerate(naver_news_links):
            if crawled_count >= 3:  
                break
            crawled_article = crawl_and_get_article(link, index + 1)
            if crawled_article is None:  
                continue  

            crawled_count += 1  

            spinner_text = [
                "첫 기사를 GPT4가 정리 하고 있습니다.",
                "다음 기사를 GPT4가 정리하고 있습니다.",
                "마지막 기사를 GPT4가 정리하고 있습니다."
            ][crawled_count - 1]  
            summarized_content += fetch_from_openai("gpt-4", [
                {"role": "user",
                 "content": f"{crawled_article['title']} 및 {crawled_article['content']} 내용들을 잘 정리해서 하나의 줄거리로 표현된 기사 스타일 보고 자료를 만들어. 어떻게든 완성도를 높여라. 제목은 쓰지마. 다루는 공통된 내용과 공통되지 않은 내용 모두 포함해 전체 내용이 잘 드러나는 보고 자료로 만들거야. 줄바꿈도 신경 써 줘. 키워드, 숫자 등을 잘 확인해. '눈길을 끌었다' '주목된다' 등 판단이나 창의적인 표현들은 빼고 2500자 이내로 써 줘. '됐다' '했다' 등 반말로 정리해. 내용 중에 [] 이 대괄호나 = 이런 부호가 들어가지 않게 해줘."}
            ], spinner_text)
        
        st.session_state.summarized_content = summarized_content
        st.write(st.session_state.summarized_content)

    prompt = st.text_area("리드문을 대략 써서 넣으세요.", height=300)

    if st.button("생성하기"):
        if len(prompt) <= 10:
            st.markdown("<span style='color:red'>10자 이상 써 주세요.</span>", unsafe_allow_html=True)
        else:
            with st.spinner('GPT-4가 기사로 만들고 있어요.'):
                article_content = fetch_from_openai("gpt-4", [
                    {"role": "user",
                     "content": f"{st.session_state.summarized_content} 를 토대로 신문 기사를 쓸거야. 1500자 내로 기사를 써 줘. 특히 숫자와 관련된 내용은 모두 나오도록 해 줘. 기사처럼 줄바꿈을 특히 잘 활용해. 앞서 작성한 리드문 '{prompt}'에서 기사를 시작해. 정리된 내용 중에서 리드문과 관련성이 높은 내용들을 중심으로 기사를 써 줘."}
                ], '좀 오래 걸릴 수 있어요 ㅎㅎ 기다려주세요.')
                st.write(article_content)

if __name__ == "__main__":
    main()
