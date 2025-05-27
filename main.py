# main.py - ByBy PC AI System with MySQL
from flask import Flask, request, jsonify, render_template_string
import mysql.connector
from difflib import get_close_matches
import os
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

app = Flask(__name__)

# ========== KẾT NỐI MYSQL ==========
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DB', 'byby_ai')
    )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tạo bảng nếu chưa tồn tại
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledge (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question VARCHAR(255),
        answer TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Thêm dữ liệu mẫu
    cursor.execute('''
    INSERT INTO knowledge (question, answer) 
    VALUES 
        ('cách reset máy tính', 'Vào Settings > Update & Security > Recovery > Reset this PC'),
        ('cài đặt phần mềm', 'Tải file cài đặt và chạy file .exe hoặc .dmg')
    ''')
    
    conn.commit()
    conn.close()

# Khởi tạo database khi chạy ứng dụng
init_db()

# ========== AI CORE ==========
class ByByAI:
    def __init__(self):
        self.responses = {
            'greet': ['Xin chào! Tôi là ByBy PC AI', 'Chào bạn!', 'Hello!'],
            'goodbye': ['Tạm biệt!', 'Hẹn gặp lại bạn!'],
            'error': 'Xin lỗi, tôi chưa hiểu yêu cầu của bạn'
        }

    def get_mysql_response(self, query, params=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        result = cursor.fetchall()
        conn.close()
        return result

    def respond(self, message):
        msg = message.lower()
        
        # Xử lý câu chào hỏi
        if any(w in msg for w in ['xin chào', 'hello', 'hi', 'chào']):
            return self.responses['greet'][0]
        
        if any(w in msg for w in ['tạm biệt', 'bye', 'goodbye']):
            return self.responses['goodbye'][0]
        
        # Tìm trong database MySQL
        try:
            # Tìm câu hỏi tương tự
            questions = [q['question'] for q in 
                        self.get_mysql_response("SELECT question FROM knowledge")]
            
            match = get_close_matches(msg, questions, n=1, cutoff=0.6)
            if match:
                result = self.get_mysql_response(
                    "SELECT answer FROM knowledge WHERE question = %s", 
                    (match[0],)
                )
                if result:
                    return result[0]['answer']
        except Exception as e:
            print("Lỗi MySQL:", e)
        
        return self.responses['error']

ai = ByByAI()

# ========== FLASK ROUTES ==========
HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>ByBy PC AI</title>
    <style>
        body { 
            font-family: 'Arial', sans-serif; 
            max-width: 800px; 
            margin: 0 auto; 
            padding: 20px; 
            background-color: #f5f5f5;
        }
        #chat-container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
        }
        #chatbox { 
            height: 400px; 
            overflow-y: auto; 
            padding: 10px;
            margin-bottom: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .user-message {
            background: #e3f2fd;
            padding: 8px 12px;
            border-radius: 18px;
            margin: 5px 0;
            display: inline-block;
            max-width: 80%;
            float: right;
            clear: both;
        }
        .bot-message {
            background: #f1f1f1;
            padding: 8px 12px;
            border-radius: 18px;
            margin: 5px 0;
            display: inline-block;
            max-width: 80%;
            float: left;
            clear: both;
        }
        #user-input {
            width: calc(100% - 90px);
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 20px;
            outline: none;
        }
        #send-btn {
            width: 80px;
            padding: 10px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            margin-left: 10px;
        }
        .clearfix::after {
            content: "";
            clear: both;
            display: table;
        }
    </style>
</head>
<body>
    <div id="chat-container">
        <h1>ByBy PC AI</h1>
        <div id="chatbox"></div>
        <div class="clearfix">
            <input type="text" id="user-input" placeholder="Nhập tin nhắn...">
            <button id="send-btn" onclick="sendMessage()">Gửi</button>
        </div>
    </div>

    <script>
        function addMessage(sender, message) {
            const chatbox = document.getElementById('chatbox');
            const msgDiv = document.createElement('div');
            msgDiv.className = sender + '-message';
            msgDiv.textContent = message;
            chatbox.appendChild(msgDiv);
            chatbox.scrollTop = chatbox.scrollHeight;
        }

        function sendMessage() {
            const input = document.getElementById('user-input');
            const message = input.value.trim();
            
            if (message) {
                addMessage('user', message);
                input.value = '';
                
                fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                })
                .then(response => response.json())
                .then(data => addMessage('bot', data.response))
                .catch(error => addMessage('bot', 'Lỗi kết nối'));
            }
        }

        // Cho phép gửi bằng phím Enter
        document.getElementById('user-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    response = ai.respond(data['message'])
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
