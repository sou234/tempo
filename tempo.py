import streamlit as st
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import requests
import urllib3
from io import BytesIO
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import feedparser
from etf_monitor import ActiveETFMonitor

# 보안 인증서 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 엑셀 다운로드용 함수
def to_excel(df_new, df_inc, df_dec, df_all, date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_new.to_excel(writer, index=False, sheet_name='신규편입')
        df_inc.to_excel(writer, index=False, sheet_name='비중확대')
        df_dec.to_excel(writer, index=False, sheet_name='비중축소')
        df_all.to_excel(writer, index=False, sheet_name='전체포트폴리오')
    processed_data = output.getvalue()
    return processed_data

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="MAS Decision Support System",
    page_icon="🍊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. 데이터 수집 함수
# ---------------------------------------------------------

@st.cache_data(ttl=600)
def fetch_market_data():
    """시장 지수 수집"""
    tickers = {"KOSPI": "KS11", "S&P500": "US500", "USD/KRW": "USD/KRW"}
    market_data, history_data = {}, {}
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    for name, ticker in tickers.items():
        try:
            df = fdr.DataReader(ticker, start_date)
            if not df.empty:
                current = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                pct = ((current - prev) / prev * 100) if prev != 0 else 0
                df['MA20'] = df['Close'].rolling(window=20).mean()
                trend = "상승 (Bull)" if current > df['MA20'].iloc[-1] else "조정 (Bear)"
                market_data[name] = {"price": current, "change": current - prev, "pct_change": pct, "trend": trend}
                history_data[name] = df
        except: pass
    return market_data, history_data

@st.cache_data(ttl=1800)
def fetch_industry_news(topic):
    """구글 뉴스 RSS를 통해 특정 토픽의 뉴스 수집"""
    # 주제별 검색 쿼리 매핑
    queries = {
        "AI & 반도체": "Nvidia OR OpenAI OR TSMC OR Samsung Electronics semiconductor",
        "2차전지 & EV": "Tesla OR CATL OR LG Energy Solution OR electric vehicle battery",
        "바이오 & 헬스케어": "Eli Lilly OR Novo Nordisk OR biotech OR FDA approval",
        "글로벌 거시경제": "Federal Reserve OR inflation OR interest rate OR US economy"
    }
    
    query = queries.get(topic, "Global Economy")
    encoded_query = requests.utils.quote(query)
    # 구글 뉴스 RSS URL (언어: 영어/한국어 섞여있을 수 있음, 여기선 US edition 사용)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    try:
        feed = feedparser.parse(rss_url)
        news_items = []
        for entry in feed.entries[:10]: # 최신 10개만
            news_items.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published,
                "source": entry.source.title if hasattr(entry, 'source') else "Google News"
            })
        return news_items
    except Exception as e:
        return []

# 데이터 로드
metrics, histories = fetch_market_data()

# ---------------------------------------------------------
# 3. 사이드바 구성
# ---------------------------------------------------------
with st.sidebar:
    st.title("🍊 Mirae Asset")
    st.subheader("고객자산배분본부")
    st.caption("Ver 2.0 - News & Rebalancing")
    st.markdown("---")
    
    menu = st.radio("메뉴 선택", ["📌 시장 동향", "📰 글로벌 산업 뉴스", "📊 타임폴리오 실시간 PDF"])
    
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()

# ---------------------------------------------------------
# 4. 메인 화면
# ---------------------------------------------------------

if menu == "📌 시장 동향":
    st.title("📈 Global Market Monitor")
    col1, col2, col3 = st.columns(3)
    with col1:
        if "KOSPI" in metrics:
            d = metrics["KOSPI"]
            st.metric("KOSPI", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%")
    with col2:
        if "S&P500" in metrics:
            d = metrics["S&P500"]
            st.metric("S&P 500", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%")
    with col3:
        if "USD/KRW" in metrics:
            d = metrics["USD/KRW"]
            st.metric("원/달러 환율", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%", delta_color="inverse")
    
    if "KOSPI" in histories:
        st.line_chart(histories['KOSPI']['Close'])

elif menu == "📰 글로벌 산업 뉴스":
    st.title("📰 Global Industry & Macro News")
    st.markdown("주요 산업 및 거시 경제 관련 최신 뉴스를 실시간으로 확인하세요.")
    
    # 탭으로 분야 구분
    topics = ["AI & 반도체", "2차전지 & EV", "바이오 & 헬스케어", "글로벌 거시경제"]
    tabs = st.tabs(topics)
    
    for i, topic in enumerate(topics):
        with tabs[i]:
            st.subheader(f"{topic} 주요 뉴스")
            news_items = fetch_industry_news(topic)
            
            if news_items:
                for item in news_items:
                    # 카드 형태의 디자인
                    with st.container():
                        st.markdown(f"### [{item['title']}]({item['link']})")
                        st.caption(f"{item['source']} | {item['published']}")
                        st.markdown("---")
            else:
                st.info("뉴스를 불러올 수 없습니다.")

elif menu == "📊 타임폴리오 실시간 PDF":
    st.title("📊 TIMEFOLIO Official Portfolio & Rebalancing")
    
    etf_categories = {
        "해외주식형 (10종)": {
            "글로벌탑픽": "22", "글로벌바이오": "9", "우주테크&방산": "20",
            "S&P500": "5", "나스닥100": "2", "글로벌AI": "6",
            "차이나AI": "19", "미국배당다우존스": "18",
            "미국나스닥100채권혼합50": "10", "글로벌소비트렌드": "8"
        },
        "국내주식형 (7종)": {
            "K신재생에너지": "16", "K바이오": "13", "Korea플러스배당": "12",
            "코스피": "11", "코리아밸류업": "15", "K이노베이션": "17", "K컬처": "1"
        }
    }
    
    c1, c2 = st.columns(2)
    with c1:
        cat = st.selectbox("분류", list(etf_categories.keys()))
    with c2:
        name = st.selectbox("상품명", list(etf_categories[cat].keys()))
    
    target_idx = etf_categories[cat][name]
    
    if st.button("데이터 분석 및 리밸런싱 요약"):
        with st.spinner(f"'{name}' 데이터를 수집 및 분석 중입니다..."):
            try:
                # ActiveETFMonitor 초기화
                monitor = ActiveETFMonitor(url=f"https://timefolioetf.co.kr/m11_view.php?idx={target_idx}", etf_name=name)
                
                # 금일 날짜 (한국 시간)
                today = datetime.now(pytz.timezone('Asia/Seoul')).strftime("%Y-%m-%d")
                
                # 금일 데이터 수집
                df_today = monitor.get_portfolio_data(today)
                monitor.save_data(df_today, today)
                
                # 전일 데이터 로드 (없으면 크롤링)
                try:
                    prev_day = monitor.get_previous_business_day(today)
                    df_prev = monitor.load_data(prev_day)
                    
                    # 리밸런싱 분석 수행
                    analysis = monitor.analyze_rebalancing(df_today, df_prev, prev_day, today)
                    analysis_success = True
                except Exception as e:
                    st.warning(f"전일 데이터를 찾을 수 없어 리밸런싱 분석을 건너뜁니다: {e}")
                    analysis_success = False
                    df_prev = None

                st.success(f"✅ {name} 데이터 분석 완료" + (f" (기준: {today} vs {prev_day})" if analysis_success else ""))

                # --- 리밸런싱 요약 (분석 성공 시) ---
                if analysis_success:
                    st.subheader("🔄 리밸런싱 정밀 분석 (시장수익률 조정 반영)")
                    
                    # 요약 메트릭
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("비중 확대", f"{len(analysis['increased_stocks'])} 종목")
                    m2.metric("비중 축소", f"{len(analysis['decreased_stocks'])} 종목")
                    m3.metric("신규 편입", f"{len(analysis['new_stocks'])} 종목")
                    m4.metric("완전 편출", f"{len(analysis['removed_stocks'])} 종목")

                    # 탭 구성
                    tab1, tab2, tab3 = st.tabs(["주요 변경내역", "세부 변동", "전체 포트폴리오"])
                    
                    with tab1:
                        # 신규 편입 & 편출
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("##### 🟢 신규 편입")
                            if analysis['new_stocks']:
                                rows = []
                                for s in analysis['new_stocks']:
                                    rows.append({
                                        "종목명": s['종목명'],
                                        "현재비중": f"{s['비중_today']:.2f}%",
                                        "순수변동": f"+{s['순수_비중변화']:.2f}%p"
                                    })
                                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                            else:
                                st.caption("신규 편입 종목 없음")

                        with c2:
                            st.markdown("##### 🔴 완전 편출")
                            if analysis['removed_stocks']:
                                rows = []
                                for s in analysis['removed_stocks']:
                                    rows.append({
                                        "종목명": s['종목명'],
                                        "이전비중": f"{s['비중_prev']:.2f}%",
                                        "순수변동": f"{s['순수_비중변화']:.2f}%p"
                                    })
                                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                            else:
                                st.caption("완전 편출 종목 없음")

                    with tab2:
                        # 비중 확대 & 축소
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("##### 🔼 비중 확대 (Top 5)")
                            if analysis['increased_stocks']:
                                df_inc = pd.DataFrame(analysis['increased_stocks'])
                                df_inc = df_inc.sort_values('순수_비중변화', ascending=False).head(5)
                                display_df = df_inc[['종목명', '비중_prev', '비중_today', '순수_비중변화']].copy()
                                display_df.columns = ['종목명', '이전(%)', '현재(%)', '변동(%p)']
                                st.dataframe(display_df.style.format({'이전(%)': '{:.2f}', '현재(%)': '{:.2f}', '변동(%p)': '+{:.2f}'}), hide_index=True, use_container_width=True)
                            else:
                                st.caption("비중 확대 종목 없음")

                        with c2:
                            st.markdown("##### 🔽 비중 축소 (Top 5)")
                            if analysis['decreased_stocks']:
                                df_dec = pd.DataFrame(analysis['decreased_stocks'])
                                df_dec = df_dec.sort_values('순수_비중변화', ascending=True).head(5)
                                display_df = df_dec[['종목명', '비중_prev', '비중_today', '순수_비중변화']].copy()
                                display_df.columns = ['종목명', '이전(%)', '현재(%)', '변동(%p)']
                                st.dataframe(display_df.style.format({'이전(%)': '{:.2f}', '현재(%)': '{:.2f}', '변동(%p)': '{:.2f}'}), hide_index=True, use_container_width=True)
                            else:
                                st.caption("비중 축소 종목 없음")
                                
                        st.info("* **순수 변동**: 시장 가격 등락에 의한 '가상 비중'을 제외한 매니저의 실제 매매로 인한 비중 변화 (추정치)")

                    with tab3:
                        st.markdown("##### 📋 전체 포트폴리오 구성")
                else:
                    # 분석 실패 시 기본 탭
                    st.subheader("📋 전체 포트폴리오 구성")

                # 전체 리스트 및 차트 (공통)
                col_chart, col_list = st.columns([1, 1])
                
                with col_chart:
                    # 파이 차트용 데이터 준비
                    chart_df = df_today.copy()
                    chart_df['비중'] = pd.to_numeric(chart_df['비중'], errors='coerce')
                    chart_df.loc[chart_df['비중'] < 1.0, '종목명'] = '기타' # 1% 미만 기타 처리
                    
                    fig = px.pie(chart_df, values="비중", names="종목명", hole=0.4, title="포트폴리오 비중",
                                color_discrete_sequence=px.colors.qualitative.Set3)
                    st.plotly_chart(fig, use_container_width=True)

                # --- [신규 기능 3] 트리맵 (히트맵) ---
                with tab3:
                    st.markdown("##### 🗺️ 포트폴리오 히트맵")
                    # 트리맵용 데이터 준비 (현금 제외)
                    tree_df = df_today[df_today['종목명'] != '현금'].copy()
                    if not tree_df.empty:
                        # 색상을 위한 등락폭 데이터가 있다면 좋겠지만, 지금은 비중 크기로만 시각화
                        # 추후 etf_monitor.py에서 등락률까지 가져오면 color='등락률' 적용 가능
                        fig_tree = px.treemap(tree_df, path=['종목명'], values='비중',
                                             color='비중', color_continuous_scale='Viridis',
                                             title=f"{name} 보유 종목 맵 (Size=비중)")
                        fig_tree.update_traces(textinfo="label+value+percent entry")
                        st.plotly_chart(fig_tree, use_container_width=True)
                    else:
                        st.info("시각화할 데이터가 없습니다.")

                    st.markdown("##### 📋 전체 포트폴리오 구성")

                # --- [신규 기능 2] 엑셀 다운로드 ---
                st.markdown("---")
                st.subheader("📥 보고서 다운로드")
                
                # 엑셀 생성을 위한 데이터 프레임 준비
                e_new = pd.DataFrame(analysis['new_stocks']) if analysis['new_stocks'] else pd.DataFrame(columns=['종목명', '비중_today', '순수_비중변화'])
                e_inc = pd.DataFrame(analysis['increased_stocks']) if analysis['increased_stocks'] else pd.DataFrame(columns=['종목명', '비중_prev', '비중_today', '순수_비중변화'])
                e_dec = pd.DataFrame(analysis['decreased_stocks']) if analysis['decreased_stocks'] else pd.DataFrame(columns=['종목명', '비중_prev', '비중_today', '순수_비중변화'])
                
                excel_data = to_excel(e_new, e_inc, e_dec, df_today, today)
                
                st.download_button(
                    label="📊 엑셀 리포트 내려받기 (.xlsx)",
                    data=excel_data,
                    file_name=f"{name}_Report_{today}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # --- [신규 기능 1] 종목 비중 히스토리 ---
                st.markdown("---")
                st.subheader("📅 종목 비중 히스토리 (최근 30일)")
                
                with st.expander("📈 개별 종목 트렌드 분석 펼치기", expanded=False):
                    history_df = monitor.load_history(days=30)
                    
                    if not history_df.empty:
                        # 종목 선택
                        all_stocks = sorted(history_df['종목명'].unique())
                        selected_stock = st.selectbox("분석할 종목을 선택하세요", all_stocks, index=0)
                        
                        # 선택 종목 데이터 필터링
                        stock_history = history_df[history_df['종목명'] == selected_stock].sort_values('날짜')
                        
                        chart = px.line(stock_history, x='날짜', y='비중', title=f"{selected_stock} 비중 변화 추이",
                                       markers=True, text='비중')
                        chart.update_traces(textposition="top center")
                        st.plotly_chart(chart, use_container_width=True)
                    else:
                        st.info("누적된 히스토리 데이터가 아직 없습니다. 매일 데이터를 수집하면 차트가 활성화됩니다.")
                
                with col_list:
                    # 간단한 리스트 출력 (상위 15개)
                    top_df = df_today[['종목명', '비중', '수량']].head(15)
                    st.dataframe(top_df.style.format({'비중': '{:.2f}%', '수량': '{:,}'}), use_container_width=True)

            except Exception as e:
                st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
                st.exception(e)

    st.markdown("---")
    st.link_button("🌐 공식 상세페이지 바로가기", f"https://timefolioetf.co.kr/m11_view.php?idx={target_idx}")
