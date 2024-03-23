from flask import Flask, render_template, request, jsonify
import os, requests,datetime
from datetime import datetime,timedelta
import pdfplumber,base64
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials, firestore,auth,storage
import uuid  # for generating random user_id
from flask_cors import CORS
from google.oauth2.service_account import Credentials
from random import randint

cred = credentials.Certificate("keys.json")
firebase_admin.initialize_app(cred,{'storageBucket': 'jam-mate.appspot.com'})
db = firestore.client()

API_KEY = 'AIzaSyCE90HdKSc18gr0ZoP3GMqvavHo3AWsB9c'

SEARCH_API_KEY="keys.json"
CSE_ID="b58c46f14303e42ac"

app = Flask(__name__)
CORS(app)  # Allow requests from localhost:5173
app.secret_key = os.urandom(24)

common_words = ['a', 'and', 'of', 'or', 'in', 'on']

# Function to extract words before colon from a PDF
def extract_words_before_colon(pdf_path):
    groups = []
    common_words = {'and', 'of', 'in', 'on', 'a'}  # Define common words to be ignored

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            if not text:
                continue

            paragraphs = text.split("\n")

            for paragraph in paragraphs:
                words = paragraph.split()
                colon_found = False  # Flag to track if a colon is found
                current_group = []  # To store the current group of words
                skip_group = False  # Flag to indicate if the current group should be skipped

                for word in words:
                    if word.endswith(":") and current_group:
                        # Check if the current group should be skipped
                        if skip_group:
                            current_group = []  # Reset the current group
                        else:
                            colon_found = True  # Set colon_found flag to True
                            # Omit the colon and add only the word to the current group
                            current_group.append(word[:-1])  # Append word without colon
                            break  # Exit the loop if a colon is found
                    else:
                        # Check if the word starts with a lowercase letter and is not a common word
                        if not word[0].isupper() and word.lower() not in common_words:
                            skip_group = True  # Set skip_group flag to True
                        current_group.append(word)  # Add the word to the current group

                # Check if a colon was found and the current group is not empty
                if colon_found and current_group:
                    groups.append(" ".join(current_group))  # Join the words in the current group and append to groups

    return groups  # Return the list of groups of words before colons

# Function to fetch top 10 YouTube videos for a given topic
def get_top_videos(topic):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.search().list(
        q=topic,
        part='snippet',
        type='video',
        maxResults=1
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
def get_authenticated_service():
    credentials = Credentials.from_service_account_file(
        SEARCH_API_KEY,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return credentials
def calculate_schedule(preferences):
    # Extract preferences
    start_date = datetime.strptime(preferences.get('startDate'), '%Y-%m-%d')
    end_date = datetime.strptime(preferences.get('endDate'), '%Y-%m-%d')
    num_revisions_needed = int(preferences.get('numRevisionsNeeded'))
    preferable_time = preferences.get('preferableTime')
    weekdays_schedule = preferences.get('weekdaysSchedule')
    weekend_schedule = preferences.get('weekendSchedule')
    topics = preferences.get('topics')

    # Calculate total number of days
    total_days = (end_date - start_date).days + 1

    # Determine the schedule preference for weekdays and weekends
    if weekdays_schedule == 'relaxed':
        weekday_hours_range = (1, 2)
    elif weekdays_schedule == 'balanced':
        weekday_hours_range = (2, 3)
    else:  # Default to balanced
        weekday_hours_range = (2, 3)

    if weekend_schedule == 'balanced':
        weekend_hours_range = (4, 5)
    elif weekend_schedule == 'tight':
        weekend_hours_range = (6, 8)
    else:  # Default to balanced
        weekend_hours_range = (4, 5)

    # Calculate total available weekdays and weekends
    total_weekdays = sum(1 for i in range(total_days) if (start_date + timedelta(days=i)).weekday() < 5)
    total_weekend = total_days - total_weekdays

    # Calculate total available hours for weekdays and weekends
    total_available_hours_weekdays = total_weekdays * randint(*weekday_hours_range)
    total_available_hours_weekend = total_weekend * randint(*weekend_hours_range)

    # Calculate total available hours
    total_available_hours = total_available_hours_weekdays + total_available_hours_weekend

    # Distribute topics evenly across the total available days
    topics_count = len(topics)
    average_hours_per_topic = total_available_hours / topics_count

    # Create schedule
    schedule = {}
    current_date = start_date
    for topic in topics:
        # Calculate study hours for the topic
        study_hours = min(randint(2, 5), average_hours_per_topic)

        # Add revision time
        current_revisions_needed = num_revisions_needed
        while current_revisions_needed > 0:
            revision_hours = randint(1, 2)  # Randomly choose revision hours between 1 and 2
            study_hours += revision_hours
            current_revisions_needed -= 1

        # Schedule topic based on preferable time
        if preferable_time == 'morning':
            study_time = (6, 8)  # Morning study time (6:00 AM - 8:00 AM)
        else:
            study_time = (19, 23)  # Evening study time (7:00 PM - 11:00 PM)

        # Adjust study time based on available hours and schedule preference
        if current_date.weekday() < 5:  # Weekday
            available_hours = randint(*weekday_hours_range)
        else:  # Weekend
            available_hours = randint(*weekend_hours_range)

        study_hours = min(study_hours, available_hours)

        study_start_time = datetime(current_date.year, current_date.month, current_date.day, *study_time)
        study_end_time = study_start_time + timedelta(hours=study_hours)

        schedule[current_date.strftime('%Y-%m-%d')] = {
            'topic': topic,
            'start_time': study_start_time.strftime('%H:%M'),
            'end_time': study_end_time.strftime('%H:%M')
        }

        # Move to the next day
        current_date += timedelta(days=1)

    return schedule



# Example Flask route to authenticate requests

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if the POST request has the file part
        if 'syllabus' not in request.files:
            print("error")
            return jsonify("Error")

        file = request.files['syllabus']


        # If the user does not select a file, browser also
        # submit an empty part without filename
        if file.filename == '':
            return jsonify("Error -2")

        if file:
            # Save the uploaded PDF file to a temporary location
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(pdf_path)

            # Extract words from the uploaded PDF file before the colon
            topics = extract_words_before_colon(pdf_path)
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

@app.route('/resource/<userid>', methods=['GET'])
def get_resource(userid):
    doc_id = userid  # Replace with the actual document ID

    doc_ref = db.collection('users').document(doc_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        events = data.get('events', [])

        # Fetch top videos for each event
        event_videos = {}
        for event in events:
            videos = get_top_videos(event+"for JAM exam")
            event_videos[event] = videos  # Take only the first two videos for each event
        print(event_videos)
        return jsonify({'event_videos': event_videos})
    else:
        return jsonify({'error': 'Document not found'})


@app.route('/search', methods=['GET'])
def search_topics():
    query = 'Economics topics for jam exam'  # Get the search query from the request

    # Authenticate using the service account key file
    credentials = get_authenticated_service()
    authed_session = requests.Session()
    authed_session.headers.update({'Authorization': f'Bearer {credentials.token}'})
    
    # Make a GET request to the Custom Search JSON API
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&cx={CSE_ID}"
    response = authed_session.get(url)
    print(response)
    if response.status_code == 200:
        data = response.json()
        topics = [item['title'] for item in data.get('items', [])]  # Extract titles of search results
        return jsonify({'topics': topics})
    else:
        return jsonify({'error': 'Failed to fetch search results'})

@app.route("/calendar/<userid>")
def calendar(userid):
    user_ref = db.collection('users').document(userid)
    
    # Fetch user preferences and topics from Firestore
    user_doc = user_ref.get()
    print(user_doc)
    if not user_doc.exists:
        return jsonify({'error': 'User not found'}), 404
    
    data = user_doc.to_dict()
    preferences = data.get('preferences')
    if not preferences:
        return jsonify({'error': 'User preferences not found'}), 404
    
    # Calculate schedule
    schedule = calculate_schedule(preferences)
    if schedule:
        print(schedule)
    
    return jsonify(schedule)
    
@app.route("/journal/<userid>", methods=["GET", "POST"])
def handle_journal(userid):
    if request.method == "GET":
        # Check if user ID exists in the database
        user_ref = db.collection("users").document(userid)
        user_data = user_ref.get()
        
        if user_data.exists:
            # User exists, fetch journal content
            journal_data = user_data.to_dict().get("journal", [])
            return jsonify(journal_data)
        else:
            # User does not exist, return empty array
            return jsonify([])

    elif request.method == "POST":
        # Get journal content from request body
        journal_content = request.json

        # Check if user ID exists in the database
        user_ref = db.collection("users").document(userid)
        user_data = user_ref.get()

        if user_data.exists:
            # User exists, update journal content
            user_ref.update({"journal": firestore.ArrayUnion([journal_content])})
            return jsonify(journal_content)
        else:
            # User does not exist, create new user
            user_ref.set({"journal": [journal_content]})
            return jsonify(journal_content)
@app.route("/preference/<userid>", methods=["GET", "POST"])
def preference(userid):
    user_ref = db.collection('users').document(userid)
    
    if request.method == "GET":
        # Check if user exists in Firestore
        user_doc = user_ref.get()
        if user_doc.exists:
            # Check if preferences exist
            preferences = user_doc.to_dict().get('preferences')
            return jsonify(preferences) if preferences else jsonify(None)
        else:
            # If user does not exist, create a new document with empty preferences
            user_ref.set({'preferences': {}})
            return jsonify(None)
    elif request.method == "POST":
        data = request.form.to_dict()
        print(data)
        # Handle file upload separately
        if 'syllabus' in request.files:
            file = request.files['syllabus']
            if file:
                # Save the uploaded PDF file to a temporary location
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(pdf_path)
                # Upload file to Firestore
                topics = extract_words_before_colon(pdf_path)
                # Update data dictionary with topics
                data['topics'] = topics
        
        # Update or save user preferences
        user_ref.set({'preferences': data})
        return jsonify(data)


def upload_file_to_firestore(file):
    # Get a reference to the default storage bucket
    bucket = storage.bucket()
    
    # Reset the file's stream to the beginning
    file.seek(0)
    
    # Upload file to Firebase Storage
    blob = bucket.blob(file.filename)
    blob.upload_from_file(file)
    
    # Get download URL for the file
    file_url = blob.generate_signed_url(timedelta(days=1), method='GET')

    return file_url

if __name__ == '__main__':
    # Create a folder to store uploaded files
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.run(debug=True)
