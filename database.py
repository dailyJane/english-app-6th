import psycopg2
import pandas as pd
import streamlit as st

def get_connection():
    # Use the DB_URL stored securely in Streamlit Secrets
    return psycopg2.connect(st.secrets["DB_URL"])

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Create USERS table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            class_name TEXT,
            student_name TEXT,
            UNIQUE(class_name, student_name)
        )
    ''')
    
    # Create SCORES table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            unit_name TEXT,
            target_text TEXT,
            recognized_text TEXT,
            score_percentage REAL,
            grade TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(class_name, student_name):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT id FROM users WHERE class_name=%s AND student_name=%s', (class_name, student_name))
    row = c.fetchone()
    
    if row is None:
        c.execute('INSERT INTO users (class_name, student_name) VALUES (%s, %s) RETURNING id', (class_name, student_name))
        conn.commit()
        user_id = c.fetchone()[0]
    else:
        user_id = row[0]
        
    conn.close()
    return user_id

def insert_score(user_id, unit_name, target_text, recognized_text, score_percentage, grade):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO scores (user_id, unit_name, target_text, recognized_text, score_percentage, grade)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (user_id, unit_name, target_text, recognized_text, score_percentage, grade))
    conn.commit()
    conn.close()

def get_user_scores(user_id):
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT unit_name, target_text, recognized_text, score_percentage, grade, timestamp
        FROM scores
        WHERE user_id = %s
        ORDER BY timestamp DESC
    ''', conn, params=(user_id,))
    conn.close()
    return df

def get_class_ranking(class_name, unit_name, user_id):
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT u.id as user_id, s.target_text, s.score_percentage
        FROM users u
        JOIN scores s ON u.id = s.user_id
        WHERE u.class_name = %s AND s.unit_name = %s
        ORDER BY s.timestamp DESC
    ''', conn, params=(class_name, unit_name))
    conn.close()
    
    if df.empty:
        return 0, 0
        
    df_latest = df.drop_duplicates(subset=['user_id', 'target_text'], keep='first')
    user_avg = df_latest.groupby('user_id')['score_percentage'].mean().reset_index()
    user_avg = user_avg.sort_values(by='score_percentage', ascending=False).reset_index(drop=True)
    user_avg['rank'] = user_avg['score_percentage'].rank(method='min', ascending=False)
    
    try:
        rank = int(user_avg[user_avg['user_id'] == user_id]['rank'].iloc[0])
    except IndexError:
        rank = 0
        
    total = len(user_avg)
    return rank, total

def get_top_students(class_name):
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT u.student_name, s.target_text, s.score_percentage
        FROM users u
        JOIN scores s ON u.id = s.user_id
        WHERE u.class_name = %s
        ORDER BY s.timestamp DESC
    ''', conn, params=(class_name,))
    conn.close()
    
    if df.empty:
        return pd.DataFrame()
        
    df_latest = df.drop_duplicates(subset=['student_name', 'target_text'], keep='first')
    user_avg = df_latest.groupby('student_name')['score_percentage'].mean().round(1).reset_index()
    user_avg = user_avg.sort_values(by='score_percentage', ascending=False).reset_index(drop=True)
    user_avg.index = user_avg.index + 1
    user_avg = user_avg.rename(columns={"student_name": "학생 이름", "score_percentage": "평균 점수"})
    return user_avg

def get_practice_kings(class_name):
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT u.student_name, COUNT(s.id) as practice_count
        FROM users u
        JOIN scores s ON u.id = s.user_id
        WHERE u.class_name = %s
        GROUP BY u.id
        ORDER BY practice_count DESC
    ''', conn, params=(class_name,))
    conn.close()
    
    if df.empty:
        return pd.DataFrame()
        
    df.index = df.index + 1
    df = df.rename(columns={"student_name": "학생 이름", "practice_count": "총 연습 횟수"})
    return df
