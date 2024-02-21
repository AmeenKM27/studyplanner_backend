from flask import Flask, render_template, request, jsonify
import os
import pdfplumber
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials, firestore
import uuid  # for generating random user_id
from flask_cors import CORS

cred = credentials.Certificate("keys.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

API_KEY = 'AIzaSyAENnjp_42ttaevBzNJIveyoBW9Ee3DZrg'

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}})  # Allow requests from localhost:5173
app.secret_key = os.urandom(24)

common_words = ['a', 'and', 'of', 'or', 'in', 'on']

# Function to extract words before colon from a PDF
def extract_words_before_colon(pdf_path):
    groups = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            if not text:
                continue

            paragraphs = text.split("\n")

            for paragraph in paragraphs:
                words = paragraph.split()
                colon_found = False
                current_group = []
                skip_group = False

                for word in words:
                    if word.endswith(":") and current_group:
                        if skip_group:
                            current_group = []
                        else:
                            colon_found = True
                            groups.append(" ".join(current_group))  # Append current group to list
                            current_group = []  # Reset current group for the next event
                            break
                    else:
                        if not word[0].isupper() and word.lower() not in common_words:
                            skip_group = True
                        current_group.append(word)

                if colon_found and current_group:
                    groups.append(" ".join(current_group))  # Append current group to list

    return groups

# Function to fetch top 10 YouTube videos for a given topic
def get_top_videos(topic):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.search().list(
        q=topic,
        part='snippet',
        type='video',
        maxResults=10
    )
    response = request.execute()
    videos = []
    for item in response['items']:
        videos.append({
            'title': item['snippet']['title'],
            'video_id': item['id']['videoId'],
            'thumbnail': item['snippet']['thumbnails']['default']['url']
        })
    return videos

# Function to add form data to Firebase
def add_form_data_to_firebase(form_data):
    user_id = str(uuid.uuid4())
    db.collection('users').document(user_id).set(form_data)
    return user_id

@app.route('/', methods=['GET', 'POST'])
def index():
    print("hhhh")
    print(request.form)
    print(request.files)
    if request.method == 'POST':
        # Check if the POST request has the file part
        if 'syllabus' not in request.files:
            print("error")
            return jsonify("Error")

        file = request.files['syllabus']

        print("Here")

        # If the user does not select a file, browser also
        # submit an empty part without filename
        if file.filename == '':
            return jsonify("Error -2")

        if file:
            print("Here-2")
            # Save the uploaded PDF file to a temporary location
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(pdf_path)

            # Extract words from the uploaded PDF file before the colon
            topics = extract_words_before_colon(pdf_path)
            print(topics)
            # Store form data in Firebase
            form_data = {
                'weeklyAvailableDays': request.form['weeklyAvailableDays'],
                'startTime': request.form['startTime'],
                'endTime': request.form['endTime'],
                'startDate': request.form['startDate'],
                'endDate': request.form['endDate'],
                'preferredDates': request.form['preferredDates'],
                'events': topics
            }

            # Add form data to Firebase
            user_id = add_form_data_to_firebase(form_data)

            print(user_id)

            # Redirect to a success page or render it inline
            return jsonify("Success")

    return render_template('index.html')

@app.route('/resource', methods=['GET'])
def get_resource():
    # Get the last preference form uploaded to Firebase
    last_preference_form = db.collection('users').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1).get()
    
    if last_preference_form:
        # Assuming 'events' field contains the resource data
        resource_data = last_preference_form[0].to_dict().get('events', [])
        return jsonify({'events': resource_data})  # Return as JSON array
    else:
        return jsonify({'error': 'No preference form found'})


if __name__ == '__main__':
    # Create a folder to store uploaded files
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.run(debug=True)
