from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from transformers import BertForQuestionAnswering, BertTokenizer
import torch
import os
import hashlib
from datetime import datetime
from googleapiclient.discovery import build
import requests

app = Flask(__name__)

# Cấu hình MySQL
app.config['MYSQL_HOST'] = 'localhost'  # Địa chỉ máy chủ MySQL
app.config['MYSQL_USER'] = 'root'       # Tên người dùng MySQL
app.config['MYSQL_PASSWORD'] = 'yourpassword'  # Mật khẩu của MySQL
app.config['MYSQL_DB'] = 'chatbot_db'  # Tên cơ sở dữ liệu MySQL
app.config['SECRET_KEY'] = os.urandom(24)

mysql = MySQL(app)

# Tải mô hình BERT và Tokenizer
model = BertForQuestionAnswering.from_pretrained("bert-large-uncased-whole-word-masking-finetuned-squad")
tokenizer = BertTokenizer.from_pretrained("bert-large-uncased-whole-word-masking-finetuned-squad")

# Cấu hình API Google Custom Search
GOOGLE_API_KEY = 'YOUR_GOOGLE_API_KEY'  # Thay bằng API Key của bạn
CX = 'YOUR_CUSTOM_SEARCH_ENGINE_ID'  # Thay bằng Custom Search Engine ID của bạn
service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)

# Cấu hình API thời tiết (OpenWeatherMap)
WEATHER_API_KEY = 'YOUR_OPENWEATHER_API_KEY'  # Thay bằng API Key của bạn
weather_url = "http://api.openweathermap.org/data/2.5/weather"

# Hàm mã hóa mật khẩu
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# Hàm kiểm tra mật khẩu
def check_password(hashed_password, input_password):
    return hashed_password == hash_password(input_password)

# Hàm trả lời câu hỏi với BERT
def get_bert_answer(question, context):
    inputs = tokenizer.encode_plus(question, context, add_special_tokens=True, return_tensors="pt")
    outputs = model(**inputs)
    answer_start_scores, answer_end_scores = outputs.start_logits, outputs.end_logits
    answer_start = torch.argmax(answer_start_scores)
    answer_end = torch.argmax(answer_end_scores)
    answer = tokenizer.convert_tokens_to_string(tokenizer.convert_ids_to_tokens(inputs['input_ids'][0][answer_start:answer_end+1]))
    return answer

# Hàm tìm kiếm thông tin từ Google
def google_search(query):
    res = service.cse().list(q=query, cx=CX).execute()
    search_results = res.get('items', [])
    
    if search_results:
        return search_results[0]['snippet']  # Lấy phần mô tả đầu tiên từ kết quả tìm kiếm
    return "Không tìm thấy thông tin liên quan trên Google."

# Hàm lấy thông tin thời tiết từ OpenWeatherMap
def get_weather(city="Hanoi"):
    params = {
        'q': city,
        'appid': WEATHER_API_KEY,
        'units': 'metric',  # Đơn vị: Celsius
        'lang': 'vi'  # Ngôn ngữ: Tiếng Việt
    }
    response = requests.get(weather_url, params=params)
    data = response.json()
    
    if data.get('cod') == 200:
        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']
        return f"Thời tiết hiện tại ở {city} là {temperature}°C, {weather_description}."
    return "Không thể lấy thông tin thời tiết."

# Bộ câu hỏi mẫu (FAQ) và câu trả lời
faq = {
    "Thời tiết hôm nay như thế nào?": get_weather(),  # Thời tiết sẽ được lấy từ API
    "Giới thiệu về Hà Nội?": "Hà Nội là thủ đô của Việt Nam, nổi tiếng với các di tích lịch sử và văn hóa như Văn Miếu, Hoàng Thành Thăng Long.",
    "Cách tính diện tích hình tròn?": "Diện tích hình tròn được tính bằng công thức A = πr², trong đó r là bán kính của hình tròn.",
    "Ai là người phát minh ra điện thoại?": "Người phát minh ra điện thoại là Alexander Graham Bell vào năm 1876.",
    "Làm thế nào để học lập trình Python?": "Để học lập trình Python, bạn có thể bắt đầu từ các khóa học miễn phí trực tuyến như Codecademy, Coursera hoặc Udemy."
}

# Đăng ký người dùng
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hash_password(password)
        
        # Kiểm tra nếu email đã tồn tại
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            flash('Email đã tồn tại', 'danger')
            return redirect(url_for('register'))
        
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password))
        mysql.connection.commit()
        cursor.close()
        flash('Đăng ký thành công! Bạn có thể đăng nhập ngay', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Đăng nhập
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        
        if user and check_password(user[2], password):  # user[2] là cột password
            session['user_id'] = user[0]  # Lưu id người dùng vào session
            return redirect(url_for('chat'))
        
        flash('Sai email hoặc mật khẩu', 'danger')
    
    return render_template('login.html')

# Trang chat và sử dụng BERT để trả lời câu hỏi
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    answer = None
    question = ""
    
    if request.method == 'POST':
        question = request.form['message']
        
        # Kiểm tra nếu câu hỏi có trong bộ câu hỏi mẫu (FAQ)
        if question in faq:
            answer = faq[question]
        else:
            # Đoạn văn mẫu (có thể được lấy từ API thời tiết hoặc bất kỳ nguồn dữ liệu nào)
            context = "Hà Nội có mùa hè nóng bức và mùa đông se lạnh. Thời tiết hôm nay rất đẹp và dễ chịu."
            
            # Sử dụng BERT để trả lời câu hỏi
            answer = get_bert_answer(question, context)
            
            # Nếu BERT không trả lời được, tra cứu Google
            if not answer or answer == "[CLS]":
                answer = google_search(question)
        
        # Lưu cuộc trò chuyện vào cơ sở dữ liệu
        cursor = mysql.connection.cursor()
        cursor.execute("INSERT INTO chats (user_id, message) VALUES (%s, %s)", (session['user_id'], f"Q: {question} A: {answer}"))
        mysql.connection.commit()
        cursor.close()
        
        flash('Câu trả lời đã được ghi nhận!', 'success')
        
    return render_template('chat.html', answer=answer, question=question)

# Đăng xuất
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Xóa user_id khỏi session
    return redirect(url_for('login'))

# Xuất lịch sử trò chuyện
@app.route('/chat-history')
def chat_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM chats WHERE user_id = %s", (session['user_id'],))
    chats = cursor.fetchall()
    cursor.close()
    
    return render_template('chat_history.html', chats=chats)

# Trang admin để xem người dùng và lịch sử trò chuyện
@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Kiểm tra nếu người dùng là admin
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT username FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    if user[0] != 'admin':  # Kiểm tra nếu người dùng không phải admin
        return redirect(url_for('chat'))
    
    # Lấy danh sách người dùng và lịch sử trò chuyện
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT * FROM chats")
    chats = cursor.fetchall()
    cursor.close()
    
    return render_template('admin.html', users=users, chats=chats)

# Xử lý lỗi 404
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
