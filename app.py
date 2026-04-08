import streamlit as st
import pandas as pd
import plotly.express as px
from difflib import SequenceMatcher
from collections import Counter
import re
from streamlit_mic_recorder import speech_to_text
import database as db

st.set_page_config(page_title="영어 말하기 훈련", page_icon="🗣️", layout="wide")

st.markdown("""
<style>
/* 일반 버튼 눌림 (통통 튀는) 효과 */
div[data-testid="stButton"] button:active,
div[data-testid="stFormSubmitButton"] button:active {
    transform: scale(0.94) !important;
    box-shadow: inset 0px 3px 5px rgba(0,0,0,0.2) !important;
    transition: all 0.1s !important;
}
/* 일반 버튼 호버 효과 */
div[data-testid="stButton"] button:hover {
    filter: brightness(1.05);
}

/* 마이크 버튼(iframe) 하단 테두리 짤림(크롭) 방지 */
iframe {
    min-height: 55px !important;
}
</style>
""", unsafe_allow_html=True)

# Initialize database
db.init_db()

# --- DATA ---
LESSON_DATA = {
    "Lesson 1: What Grade Are You In?": [
        {"target": "club", "desc": "[단어] 동아리"},
        {"target": "drum", "desc": "[단어] 드럼"},
        {"target": "grade", "desc": "[단어] 학년"},
        {"target": "guitar", "desc": "[단어] 기타"},
        {"target": "show", "desc": "[단어] 공연"},
        {"target": "ski", "desc": "[단어] 스키"},
        {"target": "song", "desc": "[단어] 노래"},
        {"target": "spell", "desc": "[단어] 철자를 쓰다/말하다"},
        {"target": "wear", "desc": "[단어] 입다/쓰다"},
        {"target": "hard", "desc": "[단어] 열심히"},
        {"target": "luck", "desc": "[단어] 운/행운"},
        {"target": "first", "desc": "[단어] 첫 번째의/1학년"},
        {"target": "second", "desc": "[단어] 두 번째의/2학년"},
        {"target": "third", "desc": "[단어] 세 번째의/3학년"},
        {"target": "fourth", "desc": "[단어] 네 번째의/4학년"},
        {"target": "fifth", "desc": "[단어] 다섯 번째의/5학년"},
        {"target": "sixth", "desc": "[단어] 여섯 번째의/6학년"},
        {"target": "What grade are you in?", "desc": "[핵심 문장] 너는 몇 학년이니?"},
        {"target": "I'm in the sixth grade.", "desc": "[핵심 문장] 나는 6학년이야."},
        {"target": "How do you spell your name?", "desc": "[핵심 문장] 네 이름의 철자가 어떻게 되니?"},
        {"target": "I play the guitar every day.", "desc": "[핵심 문장] 나는 매일 기타를 쳐."}
    ]
}
for i in range(2, 13):
    LESSON_DATA[f"Lesson {i}"] = []

# --- UTIL FUNCTIONS ---
def clean_string(s):
    # Remove punctuation and lowercase for comparison
    return re.sub(r'[^\w\s]', '', s.lower().strip())

def get_grade(score):
    if score >= 98: return "S+"
    elif score >= 95: return "S"
    elif score >= 90: return "A+"
    elif score >= 85: return "A"
    elif score >= 80: return "A-"
    elif score >= 75: return "B+"
    elif score >= 70: return "B"
    elif score >= 65: return "B-"
    elif score >= 60: return "C+"
    elif score >= 55: return "C"
    else: return "C-"

def get_grade_badge(grade):
    if grade.startswith('S'): bg, txt = "#fef08a", "#ca8a04"
    elif grade.startswith('A'): bg, txt = "#dcfce7", "#16a34a"
    elif grade.startswith('B'): bg, txt = "#dbeafe", "#2563eb"
    else: bg, txt = "#fee2e2", "#dc2626"
    return f"<span style='background-color: {bg}; color: {txt}; padding: 3px 10px; border-radius: 12px; font-weight: 900; font-size: 0.85em; margin-left: 5px;'>{grade}</span>"

def get_detailed_feedback(df):
    b_c = df[df['grade'].str.startswith(('B', 'C'))]
    if b_c.empty:
        return "💡 **선생님의 코칭:** 완벽 그 자체! 더 이상 연습할 부분이 보이지 않아요. 아주 훌륭합니다! 💯"
        
    weak_words = []
    # df could be coming from DB (has 'recognized_text') or session_state (has 'recognized')
    for _, row in b_c.iterrows():
        target_col = 'target_text' if 'target_text' in row else 'target'
        rec_col = 'recognized_text' if 'recognized_text' in row else 'recognized'
        
        target_str = clean_string(str(row.get(target_col, '')))
        rec_str = clean_string(str(row.get(rec_col, '')))
        
        for w in target_str.split():
            if w not in rec_str.split():
                if len(w) > 1: # Ignore single letter words to make feedback meaningful
                    weak_words.append(w)
                    
    if weak_words:
        top_weak = [w for w, c in Counter(weak_words).most_common(3)]
        weak_str = ", ".join([f"**'{w}'**" for w in top_weak])
        return f"💡 **선생님의 코칭:** 인식 결과를 분석해 보니 특히 {weak_str} 단어 발음이 기계에 잘 들리지 않았어요! 이 단어들에 주의해서 천천히 다시 연습해보세요. 💪"
    else:
        # Fallback if no specific word is found
        score_col = 'score_percentage' if 'score_percentage' in b_c else 'score'
        worst_row = b_c.loc[b_c[score_col].idxmin()]
        worst_target = worst_row['target_text' if 'target_text' in worst_row else 'target']
        return f"💡 **선생님의 코칭:** **'{worst_target}'** 문장이 조금 어려웠나봐요! 이 문장만 몇 번 더 큰 소리로 연습해 보세요. 🚀"

def calculate_similarity_and_feedback(target, recognized):
    # Use sequence matcher for words
    words_t = clean_string(target).split()
    words_r = clean_string(recognized).split()
    
    # Calculate overall similarity using python's sequence matcher on raw cleaned text
    seq_match = SequenceMatcher(None, clean_string(target), clean_string(recognized))
    score_percentage = seq_match.ratio() * 100
    
    grade = get_grade(score_percentage)

    # Naive word-level matching for feedback
    native_words = []
    need_practice_words = []
    
    for wt in words_t:
        if any(SequenceMatcher(None, wt, wr).ratio() > 0.8 for wr in words_r):
            native_words.append(wt)
        else:
            need_practice_words.append(wt)
            
    return score_percentage, grade, native_words, need_practice_words

# --- SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "student_name" not in st.session_state:
    st.session_state.student_name = ""
if "class_name" not in st.session_state:
    st.session_state.class_name = ""

# --- LOGIN PAGE ---
def login_page():
    st.markdown("<h1 style='text-align: center; color: #4CAF50;'>🎒 영어 말하기 훈련 앱에 오신 걸 환영해요! 🎒</h1>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("### 🙋 나의 정보 입력하기")
        c_name = st.selectbox("몇 반인가요?", ["1반", "2반", "3반"])
        s_name = st.text_input("나의 이름을 적어주세요!", placeholder="예: 홍길동")
        
        if st.button("🚀 교실로 입장하기!", use_container_width=True):
            if s_name.strip() == "":
                st.warning("이름을 꼭 적어주세요!")
            else:
                user_id = db.get_or_create_user(c_name, s_name)
                st.session_state.user_id = user_id
                st.session_state.student_name = s_name
                st.session_state.class_name = c_name
                st.session_state.logged_in = True
                st.rerun()

# --- MAIN APP ---
def main_app():
    # Sidebar
    st.sidebar.markdown(f"**👤 {st.session_state.student_name}** 학생 ({st.session_state.class_name})")
    if st.sidebar.button("🚪 로그아웃"):
        st.session_state.logged_in = False
        st.rerun()
    st.sidebar.write("---")
    
    menu = st.sidebar.radio("📚 메뉴를 선택하세요", ["🎙️ 말하기 테스트", "📋 내 테스트 결과 확인", "📊 나의 통계"])
    
    if menu == "🎙️ 말하기 테스트":
        test_page()
    elif menu == "📋 내 테스트 결과 확인":
        summary_page()
    elif menu == "📊 나의 통계":
        statistics_page()

def test_page():
    st.title("🎙️ 말하기 연습 (Speaking Test)")
    
    with st.container(border=True):
        st.markdown("#### 📖 먼저 학습할 단원을 선택해 주세요!")
        selected_lesson = st.selectbox("단원 선택", list(LESSON_DATA.keys()), label_visibility="collapsed")
    
    items = LESSON_DATA[selected_lesson]
    
    if not items:
        st.info("이 단원의 콘텐츠는 곧 업데이트될 예정입니다! 🛠️")
        return
        
    st.write("---")
    
    # State keeping for the current item
    if "current_item_idx" not in st.session_state or st.session_state.current_lesson != selected_lesson:
        st.session_state.current_item_idx = 0
        st.session_state.current_lesson = selected_lesson
        st.session_state.test_results = []
    
    idx = st.session_state.current_item_idx
    if idx >= len(items):
        show_test_summary(items, selected_lesson)
        return
    item = items[idx]
    target_text = item["target"]
    desc_text = item["desc"]
    
    st.markdown(f"#### 학습 진행도 ({idx + 1} / {len(items)})")
    st.progress((idx + 1) / len(items))
    
    # Show Target Card
    st.markdown(f"""
        <div style="background-color: #f0fdf4; padding: 20px; border-radius: 15px; text-align: center; border: 2px solid #bbf7d0;">
            <p style="font-size: 1.2rem; color: #166534; margin: 0;">{desc_text}</p>
            <h2 style="color: #15803d; font-size: 2.5rem; margin: 10px 0;">{target_text}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    st.write("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("👇 **버튼을 누르고 영어로 말해보세요!**")
        # Speech to text recorder
        text = speech_to_text("마이크 켜기 🔴", "정지하기 ⏹️", language='en-US', key=f"recorder_{target_text}_{idx}", use_container_width=True)
        
        if text:
            score, grade, native, practice = calculate_similarity_and_feedback(target_text, text)
            
            # Save to DB
            db.insert_score(st.session_state.user_id, selected_lesson, target_text, text, score, grade)
            
            # Save to session results
            if len(st.session_state.test_results) == idx:
                st.session_state.test_results.append({
                    "target": target_text,
                    "recognized": text,
                    "grade": grade,
                    "score": round(score, 1)
                })
            elif len(st.session_state.test_results) > idx:
                st.session_state.test_results[idx] = {
                    "target": target_text,
                    "recognized": text,
                    "grade": grade,
                    "score": round(score, 1)
                }
            
            st.write("---")
            st.markdown("### 🏆 결과 확인")
            
            # Display Grade beautifully
            grade_color = {"S": "#ca8a04", "A": "#16a34a", "B": "#2563eb", "C": "#dc2626"}.get(grade[0] if grade else "C", "black")
            st.markdown(f"<h1 style='color: {grade_color}; text-align: center;'>등급: {grade} ({score:.1f}점)</h1>", unsafe_allow_html=True)
            
            st.markdown(f"**내가 한 말:** {text}")
            
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                native_msg = ", ".join(native) if native else "더 크게 또박또박 말해볼까요?"
                st.success(f"**🌟 칭찬해요 (Native-like):**\n\n{native_msg}")
            with col_f2:
                if practice:
                    prac_msg = ", ".join(practice)
                    st.warning(f"**💪 연습이 필요해요:**\n\n{prac_msg}")
                else:
                    st.success("**🎉 완벽합니다! 다 맞췄어요!**")
            
            if st.button("➡️ 다음 문제로 넘어가기" if idx < len(items) - 1 else "📊 결과 보러가기", use_container_width=True):
                st.session_state.current_item_idx += 1
                st.rerun()

def show_test_summary(items, selected_lesson):
    st.balloons()
    st.success("단원을 모두 완료했습니다! 짝짝짝! 👏")
    st.write("---")
    st.markdown("## 📋 나의 학습 결과 요약")
    
    results = st.session_state.get("test_results", [])
    
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        s_cnt = sum(df_res['grade'].str.startswith('S'))
        a_cnt = sum(df_res['grade'].str.startswith('A'))
        b_cnt = sum(df_res['grade'].str.startswith('B'))
        c_cnt = sum(df_res['grade'].str.startswith('C'))
        
        with st.container(border=True):
            st.markdown("<h4 style='margin-top: 0;'>📊 등급 획득 수</h4>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div style='text-align: center;'>{get_grade_badge('S')}<br><br><b style='font-size: 1.5em;'>{s_cnt}개</b></div>", unsafe_allow_html=True)
            c2.markdown(f"<div style='text-align: center;'>{get_grade_badge('A')}<br><br><b style='font-size: 1.5em;'>{a_cnt}개</b></div>", unsafe_allow_html=True)
            c3.markdown(f"<div style='text-align: center;'>{get_grade_badge('B')}<br><br><b style='font-size: 1.5em;'>{b_cnt}개</b></div>", unsafe_allow_html=True)
            c4.markdown(f"<div style='text-align: center;'>{get_grade_badge('C')}<br><br><b style='font-size: 1.5em;'>{c_cnt}개</b></div>", unsafe_allow_html=True)
        
        st.write("<br>", unsafe_allow_html=True)
        
        rank, total = db.get_class_ranking(st.session_state.class_name, selected_lesson, st.session_state.user_id)
        if total > 0 and rank > 0:
            with st.container(border=True):
                st.markdown(f"<h4 style='margin-top: 0;'>🏆 {st.session_state.class_name} 우리 반 명예의 전당</h4>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='text-align: center; margin: 5px 0;'>내 전체 순위: <span style='color: #2563eb;'>{rank}등</span> / {total}명 🏃‍♂️</h3>", unsafe_allow_html=True)
            st.write("<br>", unsafe_allow_html=True)
        
        df_display = df_res.rename(columns={"target": "단어/문장", "grade": "등급", "score": "점수"})
        
        good_ones = df_res[df_res['grade'].str.startswith(('S', 'A'))]
        practice_ones = df_res[df_res['grade'].str.startswith(('B', 'C'))]
        
        feedback_msg = get_detailed_feedback(df_res)
        st.info(feedback_msg)
        st.write("<br>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("<h3 style='color: #16a34a; margin-top: 0;'>🌟 아주 잘했어요!</h3>", unsafe_allow_html=True)
                for _, row in good_ones.iterrows():
                    st.markdown(f"- **{row['target']}** {get_grade_badge(row['grade'])}", unsafe_allow_html=True)
                if good_ones.empty:
                    st.write("조금만 더 연습해보아요! 화이팅! 💪")
                
        with col2:
            with st.container(border=True):
                st.markdown("<h3 style='color: #dc2626; margin-top: 0;'>💪 연습이 더 필요해요</h3>", unsafe_allow_html=True)
                for _, row in practice_ones.iterrows():
                    st.markdown(f"- **{row['target']}** {get_grade_badge(row['grade'])}", unsafe_allow_html=True)
                if practice_ones.empty:
                    st.write("모두 완벽합니다! 🎉")
                
        st.write("---")
        st.markdown("#### 🔍 전체 세부 결과표")
        st.dataframe(df_display, use_container_width=True)
    
    st.write("<br>", unsafe_allow_html=True)
    if st.button("🔄 이 단원 다시 학습하기", use_container_width=True):
        st.session_state.current_item_idx = 0
        st.session_state.test_results = []
        st.rerun()

def statistics_page():
    st.title("📊 나의 통계 (My Statistics)")
    
    df = db.get_user_scores(st.session_state.user_id)
    
    if df.empty:
        st.info("아직 학습 기록이 없습니다. 먼저 테스트 메뉴에서 학습을 시작해보세요! 🏃‍♂️")
        return
        
    st.markdown("#### 📖 단원별 상세 기록")
    unique_units = df['unit_name'].unique()
    for unit in unique_units:
        unit_df = df[df['unit_name'] == unit]
        avg_score = unit_df['score_percentage'].mean()
        
        avg_grade = get_grade(avg_score)
        
        grade_emoji = {"S": "🏆", "A": "🌟", "B": "💪", "C": "🔧"}.get(avg_grade[0] if avg_grade else "C", "🔧")
        
        with st.expander(f"{grade_emoji} {unit} | ⭐ 평균 등급: {avg_grade} ({avg_score:.1f}점)"):
            st.dataframe(unit_df[['target_text', 'score_percentage', 'grade', 'timestamp']].rename(
                columns={"target_text": "연습 문장", "score_percentage": "점수", "grade": "등급", "timestamp": "시간"}
            ), use_container_width=True)
            
    st.write("---")
    
    # Average score over time (last 20 attempts)
    df_chart = df.copy()
    df_chart = df_chart.sort_values('timestamp')
    df_chart['attempt'] = range(1, len(df_chart) + 1)
    
    fig = px.line(df_chart, x='attempt', y='score_percentage', markers=True, 
                  title="📈 나의 성장 그래프 (과거부터 최근까지)",
                  labels={'attempt': '도전 횟수', 'score_percentage': '점수(%)'})
    
    fig.update_layout(yaxis_range=[0,105])
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("#### 단원별 성취도")
    avg_per_unit = df.groupby('unit_name')['score_percentage'].mean().reset_index()
    fig_bar = px.bar(avg_per_unit, x='unit_name', y='score_percentage', color='score_percentage',
                     title="📊 단원별 평균 점수",
                     labels={'unit_name': '단원', 'score_percentage': '평균 점수(%)'},
                     color_continuous_scale='Blues')
    fig_bar.update_layout(yaxis_range=[0,105])
    st.plotly_chart(fig_bar, use_container_width=True)

def summary_page():
    st.title("📋 내 테스트 결과 확인")
    
    with st.container(border=True):
        st.markdown("#### 📖 결과를 확인할 단원을 선택해 주세요!")
        selected_lesson = st.selectbox("단원 선택", list(LESSON_DATA.keys()), label_visibility="collapsed")
    
    df = db.get_user_scores(st.session_state.user_id)
    if df.empty:
        st.info("아직 학습 기록이 없습니다! 먼저 🎙️ 말하기 테스트 메뉴에서 연습을 진행해주세요.")
        return
        
    df_lesson = df[df['unit_name'] == selected_lesson]
    if df_lesson.empty:
        st.info(f"[{selected_lesson}] 단원의 학습 기록이 아직 없습니다. 테스트를 먼저 진행해주세요!")
        return
        
    # 여러 번 연습했을 경우 최근 기록만 남김
    df_latest = df_lesson.drop_duplicates(subset=['target_text'], keep='first').copy()
    
    st.markdown(f"### 📊 {selected_lesson} 최근 학습 결과 요약")
    
    s_cnt = sum(df_latest['grade'].str.startswith('S'))
    a_cnt = sum(df_latest['grade'].str.startswith('A'))
    b_cnt = sum(df_latest['grade'].str.startswith('B'))
    c_cnt = sum(df_latest['grade'].str.startswith('C'))
    
    with st.container(border=True):
        st.markdown("<h4 style='margin-top: 0;'>📊 등급 획득 수</h4>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"<div style='text-align: center;'>{get_grade_badge('S')}<br><br><b style='font-size: 1.5em;'>{s_cnt}개</b></div>", unsafe_allow_html=True)
        c2.markdown(f"<div style='text-align: center;'>{get_grade_badge('A')}<br><br><b style='font-size: 1.5em;'>{a_cnt}개</b></div>", unsafe_allow_html=True)
        c3.markdown(f"<div style='text-align: center;'>{get_grade_badge('B')}<br><br><b style='font-size: 1.5em;'>{b_cnt}개</b></div>", unsafe_allow_html=True)
        c4.markdown(f"<div style='text-align: center;'>{get_grade_badge('C')}<br><br><b style='font-size: 1.5em;'>{c_cnt}개</b></div>", unsafe_allow_html=True)
    
    st.write("<br>", unsafe_allow_html=True)
    
    rank, total = db.get_class_ranking(st.session_state.class_name, selected_lesson, st.session_state.user_id)
    if total > 0 and rank > 0:
        with st.container(border=True):
            st.markdown(f"<h4 style='margin-top: 0;'>🏆 {st.session_state.class_name} 우리 반 명예의 전당</h4>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center; margin: 5px 0;'>내 전체 순위: <span style='color: #2563eb;'>{rank}등</span> / {total}명 🏃‍♂️</h3>", unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)
    
    df_latest['score_percentage'] = df_latest['score_percentage'].round(1)
    
    df_display = df_latest[['target_text', 'grade', 'score_percentage']].rename(
        columns={"target_text": "단어/문장", "grade": "최근 등급", "score_percentage": "최근 점수"}
    )
    
    good_ones = df_latest[df_latest['grade'].str.startswith(('S', 'A'))]
    practice_ones = df_latest[df_latest['grade'].str.startswith(('B', 'C'))]
    
    feedback_msg = get_detailed_feedback(df_latest)
    st.info(feedback_msg)
    st.write("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("<h3 style='color: #16a34a; margin-top: 0;'>🌟 아주 잘했어요!</h3>", unsafe_allow_html=True)
            for _, row in good_ones.iterrows():
                st.markdown(f"- **{row['target_text']}** {get_grade_badge(row['grade'])}", unsafe_allow_html=True)
            if good_ones.empty:
                st.write("조금만 더 연습해보아요! 화이팅! 💪")
                
    with col2:
        with st.container(border=True):
            st.markdown("<h3 style='color: #dc2626; margin-top: 0;'>💪 연습이 더 필요해요</h3>", unsafe_allow_html=True)
            for _, row in practice_ones.iterrows():
                st.markdown(f"- **{row['target_text']}** {get_grade_badge(row['grade'])}", unsafe_allow_html=True)
            if practice_ones.empty:
                st.write("모두 완벽합니다! 🎉")
            
    st.write("---")
    st.markdown("#### 🔍 전체 세부 결과표")
    st.dataframe(df_display, use_container_width=True)

# --- ROUTER ---
if st.session_state.logged_in:
    main_app()
else:
    login_page()
