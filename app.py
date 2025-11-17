from flask import Flask, render_template, request, flash, redirect, url_for, send_file, jsonify, session
import random
import requests
from bs4 import BeautifulSoup
import os
import re
import json
import sqlite3
import datetime
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'mcq_generator_secret_key_2024'
app.config['SESSION_TYPE'] = 'filesystem'

# PDF handling
PDF_SUPPORT = False
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
    print("✓ PDF support enabled")
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_SUPPORT = True
        print("✓ PDF support enabled (PyPDF2)")
    except ImportError:
        print("✗ PDF support disabled")

# Database initialization
def init_db():
    conn = sqlite3.connect('mcqs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS generated_mcqs
                 (id INTEGER PRIMARY KEY, 
                  question TEXT, 
                  options TEXT, 
                  correct_answer TEXT, 
                  explanation TEXT, 
                  category TEXT,
                  difficulty TEXT,
                  created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS test_results
                 (id INTEGER PRIMARY KEY,
                  total_questions INTEGER,
                  score INTEGER,
                  percentage REAL,
                  created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def extract_text_from_pdf(pdf_file):
    if not PDF_SUPPORT:
        return "PDF processing not available. Please install pypdf."
    try:
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def extract_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return ' '.join(chunk for chunk in chunks if chunk)
    except Exception as e:
        return f"Error processing URL: {str(e)}"

def preprocess_text(text):
    text = re.sub(r'\s+', ' ', text)
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]

def generate_enhanced_mcqs(text, num_questions=5):
    sentences = preprocess_text(text)
    
    if not sentences:
        return [{
            'question': 'Insufficient text to generate questions.',
            'options': {'A': 'Add more content', 'B': 'Try different text', 'C': 'Text too short', 'D': 'Insufficient data'},
            'correct_answer': 'D',
            'explanation': 'Please provide more substantial text content.',
            'category': 'General',
            'difficulty': 'Easy'
        }]
    
    mcqs = []
    
    question_templates = [
        "What is mentioned about '{}' in the text?",
        "Which detail is provided regarding '{}'?",
        "What information is given about '{}'?",
        "How is '{}' described in the content?",
        "What aspect of '{}' is highlighted?"
    ]
    
    option_sets = [
        {'A': 'Professional role', 'B': 'Educational background', 'C': 'Key achievement', 'D': 'Personal quality'},
        {'A': 'Technical function', 'B': 'Strategic importance', 'C': 'Operational detail', 'D': 'Main responsibility'},
        {'A': 'Primary purpose', 'B': 'Main contribution', 'C': 'Significant impact', 'D': 'Essential feature'},
        {'A': 'Core expertise', 'B': 'Methodology used', 'C': 'Result achieved', 'D': 'Skill demonstrated'}
    ]
    
    # Detect content type
    content_type = "General"
    text_lower = text.lower()
    if any(word in text_lower for word in ['teacher', 'school', 'education', 'student']):
        content_type = "Education"
    elif any(word in text_lower for word in ['technology', 'software', 'computer', 'digital']):
        content_type = "Technology"
    elif any(word in text_lower for word in ['business', 'company', 'organization']):
        content_type = "Business"
    
    for i in range(min(num_questions, len(sentences))):
        sentence = sentences[i]
        if len(sentence) < 25:
            continue
            
        words = sentence.split()[:6]
        key_phrase = ' '.join(words)
        
        # Determine difficulty
        word_count = len(sentence.split())
        if word_count > 20:
            difficulty = "Hard"
        elif word_count > 12:
            difficulty = "Medium"
        else:
            difficulty = "Easy"
        
        mcq = {
            'question': random.choice(question_templates).format(key_phrase),
            'options': random.choice(option_sets),
            'correct_answer': random.choice(['A', 'B', 'C', 'D']),
            'explanation': 'This question tests understanding of the text content.',
            'category': content_type,
            'difficulty': difficulty
        }
        mcqs.append(mcq)
    
    # Save to database
    save_to_db(mcqs)
    
    return mcqs

def save_to_db(mcqs):
    try:
        conn = sqlite3.connect('mcqs.db')
        c = conn.cursor()
        for mcq in mcqs:
            c.execute('''INSERT INTO generated_mcqs 
                        (question, options, correct_answer, explanation, category, difficulty)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (mcq['question'], json.dumps(mcq['options']), mcq['correct_answer'],
                      mcq['explanation'], mcq['category'], mcq['difficulty']))
        conn.commit()
        conn.close()
        print(f"✓ Saved {len(mcqs)} MCQs to database")
    except Exception as e:
        print(f"Database error: {e}")

def save_test_result(score, total):
    try:
        conn = sqlite3.connect('mcqs.db')
        c = conn.cursor()
        percentage = (score / total) * 100 if total > 0 else 0
        c.execute('INSERT INTO test_results (total_questions, score, percentage) VALUES (?, ?, ?)',
                 (total, score, percentage))
        conn.commit()
        conn.close()
        print(f"✓ Saved test result: {score}/{total} ({percentage:.1f}%)")
    except Exception as e:
        print(f"Test save error: {e}")

def get_analytics():
    try:
        conn = sqlite3.connect('mcqs.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM generated_mcqs")
        total_q = c.fetchone()[0] or 0
        
        c.execute("SELECT category, COUNT(*) FROM generated_mcqs GROUP BY category")
        categories = dict(c.fetchall())
        
        c.execute("SELECT difficulty, COUNT(*) FROM generated_mcqs GROUP BY difficulty")
        difficulties = dict(c.fetchall())
        
        c.execute("SELECT AVG(percentage) FROM test_results")
        avg_score = c.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_questions': total_q,
            'categories': categories,
            'difficulties': difficulties,
            'avg_score': round(avg_score, 1)
        }
    except Exception as e:
        print(f"Analytics error: {e}")
        return {'total_questions': 0, 'categories': {}, 'difficulties': {}, 'avg_score': 0}

@app.route('/')
def index():
    return render_template('index.html', pdf_support=PDF_SUPPORT)

@app.route('/generate', methods=['POST'])
def generate_mcqs():
    try:
        text_input = request.form.get('manual_input', '').strip()
        url_input = request.form.get('url_link', '').strip()
        num_questions = int(request.form.get('num_questions', 5))
        
        if num_questions > 30:
            flash('Maximum 30 questions allowed.')
            return redirect('/')
        
        text = ""
        source = "Text Input"
        
        if text_input:
            text = text_input
        elif url_input:
            text = extract_text_from_url(url_input)
            source = f"URL: {url_input}"
            if "Error" in text:
                flash(text)
                return redirect('/')
        elif 'pdf_file' in request.files:
            pdf_file = request.files['pdf_file']
            if pdf_file.filename:
                if PDF_SUPPORT:
                    text = extract_text_from_pdf(pdf_file)
                    source = f"PDF: {pdf_file.filename}"
                    if "Error" in text:
                        flash(text)
                        return redirect('/')
        
        if not text or len(text) < 50:
            flash('Please provide sufficient text (50+ characters).')
            return redirect('/')
        
        mcqs = generate_enhanced_mcqs(text, num_questions)
        
        # Store in session
        session['mcqs'] = mcqs
        session['source'] = source
        session['text_preview'] = text[:200] + '...' if len(text) > 200 else text
        session['generated_at'] = datetime.datetime.now().isoformat()
        
        print(f"✓ Generated {len(mcqs)} MCQs and stored in session")
        
        return render_template('mcqs.html',
                             mcqs=mcqs,
                             input_text=session['text_preview'],
                             num_generated=len(mcqs),
                             input_source=source)
        
    except Exception as e:
        flash(f'Error generating MCQs: {str(e)}')
        return redirect('/')

@app.route('/result')
def result():
    try:
        mcqs = session.get('mcqs', [])
        analytics_data = get_analytics()
        
        # Prepare chart data on server side
        category_counts = {}
        difficulty_counts = {}
        
        for mcq in mcqs:
            # Count categories
            category = mcq['category']
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # Count difficulties
            difficulty = mcq['difficulty']
            difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1
        
        print(f"✓ Rendering result page with {len(mcqs)} MCQs")
        print(f"✓ Categories: {category_counts}")
        print(f"✓ Difficulties: {difficulty_counts}")
        
        return render_template('result.html',
                             mcqs=mcqs,
                             input_source=session.get('source', ''),
                             input_text=session.get('text_preview', ''),
                             analytics=analytics_data,
                             category_counts=category_counts,
                             difficulty_counts=difficulty_counts)
    except Exception as e:
        flash(f'Error loading results: {str(e)}')
        return redirect('/')

@app.route('/download_pdf')
def download_pdf():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, height - 100, "Generated MCQs")
        
        mcqs = session.get('mcqs', [])
        y = height - 130
        
        for i, mcq in enumerate(mcqs, 1):
            if y < 100:
                p.showPage()
                y = height - 100
            
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y, f"Q{i}: {mcq['question']}")
            y -= 20
            
            p.setFont("Helvetica", 11)
            for opt, text in mcq['options'].items():
                p.drawString(70, y, f"{opt}. {text}")
                y -= 15
            
            p.setFont("Helvetica-Bold", 11)
            p.drawString(70, y, f"Answer: {mcq['correct_answer']}")
            y -= 20
            y -= 10
        
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='mcqs.pdf')
    except Exception as e:
        return f"PDF Error: {str(e)}"

@app.route('/test_mode')
def test_mode():
    try:
        mcqs = session.get('mcqs', [])
        if not mcqs:
            flash('Please generate MCQs first.')
            return redirect('/')
        
        print(f"✓ Starting test mode with {len(mcqs)} questions")
        
        # Pass timer in seconds (e.g., 10 minutes = 600 seconds)
        # You can adjust this, e.g., 1 minute per question
        timer_duration = len(mcqs) * 60 # 1 minute per question
        
        return render_template('test_mode.html', 
                             mcqs=mcqs, 
                             timer=timer_duration)
    except Exception as e:
        flash(f'Error starting test: {str(e)}')
        return redirect('/')

@app.route('/submit_test', methods=['POST'])
def submit_test():
    try:
        user_answers = request.form.to_dict()
        mcqs = session.get('mcqs', [])
        
        if not mcqs:
            flash('No MCQs found. Please generate questions first.')
            return redirect('/')
        
        print(f"✓ Processing test submission for {len(mcqs)} questions")
        print(f"✓ User answers received: {user_answers}")
        
        score = 0
        results = []
        
        for i, mcq in enumerate(mcqs, 1):
            question_key = f'q{i}'  # This matches the radio button name="q1", "q2", etc.
            user_answer = user_answers.get(question_key, '')
            correct_answer = mcq.get('correct_answer', '')
            is_correct = (user_answer == correct_answer)
            
            print(f"Question {i}: User answered '{user_answer}', Correct is '{correct_answer}', Correct: {is_correct}")
            
            if is_correct:
                score += 1
            
            results.append({
                'question_number': i,
                'question': mcq['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'explanation': mcq['explanation'],
                'options': mcq['options']
            })
        
        percentage = (score / len(mcqs)) * 100 if mcqs else 0
        
        # Save test results
        save_test_result(score, len(mcqs))
        
        # Store detailed results in session
        session['test_results'] = {
            'score': score,
            'total': len(mcqs),
            'percentage': percentage,
            'results': results
        }
        
        print(f"✓ Test completed: {score}/{len(mcqs)} ({percentage:.1f}%)")
        print(f"✓ Correct answers: {score}, Incorrect: {len(mcqs) - score}")
        
        return redirect('/test_results')
        
    except Exception as e:
        print(f"✗ Error in submit_test: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error submitting test: {str(e)}')
        return redirect('/')

@app.route('/test_results')
def test_results():
    try:
        results = session.get('test_results')
        if not results:
            flash('No test results found. Please take a test first.')
            return redirect('/')
        
        print(f"✓ Displaying test results: {results['score']}/{results['total']}")
        
        return render_template('test_results.html', results=results)
    except Exception as e:
        flash(f'Error loading test results: {str(e)}')
        return redirect('/')

@app.route('/analytics')
def analytics():
    try:
        analytics_data = get_analytics()
        return render_template('analytics.html', analytics=analytics_data)
    except Exception as e:
        flash(f'Error loading analytics: {str(e)}')
        return redirect('/')

@app.route('/export_json')
def export_json():
    try:
        mcqs = session.get('mcqs', [])
        return jsonify({
            'mcqs': mcqs,
            'metadata': {
                'count': len(mcqs),
                'generated_at': session.get('generated_at', ''),
                'source': session.get('source', '')
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    print("🚀 MCQ Generator Running: http://localhost:5000")
    print("✓ All routes are configured")
    app.run(debug=True, port=5000)