import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_FILENAME = 'english_app.db'

def get_connection():
    # Return a connection to SQLite DB
    return sqlite3.connect(DB_FILENAME)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Create USERS table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT,
            student_name TEXT,
            UNIQUE(class_name, student_name)
        )
    ''')
    
    # Create SCORES table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            unit_name TEXT,
            target_text TEXT,
            recognized_text TEXT,
            score_percentage REAL,
            grade TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(class_name, student_name):
    conn = get_connection()
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT id FROM users WHERE class_name=? AND student_name=?', (class_name, student_name))
    row = c.fetchone()
    
    if row is None:
        # Create new user
        c.execute('INSERT INTO users (class_name, student_name) VALUES (?, ?)', (class_name, student_name))
        conn.commit()
        user_id = c.lastrowid
    else:
        user_id = row[0]
        
    conn.close()
    return user_id

def insert_score(user_id, unit_name, target_text, recognized_text, score_percentage, grade):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO scores (user_id, unit_name, target_text, recognized_text, score_percentage, grade)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, unit_name, target_text, recognized_text, score_percentage, grade))
    conn.commit()
    conn.close()

def get_user_scores(user_id):
    conn = get_connection()
    # Use pandas to load directly into a dataframe
    df = pd.read_sql_query('''
        SELECT unit_name, target_text, recognized_text, score_percentage, grade, timestamp
        FROM scores
        WHERE user_id = ?
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
        WHERE u.class_name = ? AND s.unit_name = ?
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
