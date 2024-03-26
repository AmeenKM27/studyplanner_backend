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
from random import randint, shuffle

cred = credentials.Certificate("keys.json")
firebase_admin.initialize_app(cred,{'storageBucket': 'jam-mate.appspot.com'})
db = firestore.client()

API_KEY = 'AIzaSyAENnjp_42ttaevBzNJIveyoBW9Ee3DZrg'

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
        video_id = item['id']['videoId']
        title = item['snippet']['title']
        thumbnail = item['snippet']['thumbnails']['default']['url']
        
        videos.append({
            'title': title,
            'video_id': video_id,
            'thumbnail': thumbnail,
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

    # Calculate additional cycles needed
    total_cycles_needed = num_revisions_needed + 1

    # Create schedule
    schedule = {}
    current_date = start_date
    cycle_counter = 0
    while cycle_counter < total_cycles_needed and current_date <= end_date:
        # Shuffle topics for each cycle
        shuffled_topics = topics[:]
        shuffle(shuffled_topics)
        
        for topic in shuffled_topics:
            # Calculate study hours for the topic
            study_hours = min(randint(1, 4), average_hours_per_topic)

            # Adjust study time based on available hours and schedule preference
            if current_date.weekday() < 5:  # Weekday
                available_hours = randint(*weekday_hours_range)
            else:  # Weekend
                available_hours = randint(*weekend_hours_range)

            study_hours = min(study_hours, available_hours)

            # Schedule topic based on preferable time
            if preferable_time == 'morning':
                study_start_time = datetime(current_date.year, current_date.month, current_date.day, 6, 0)  # Morning study time (6:00 AM)
                study_end_time = study_start_time + timedelta(hours=study_hours)
            else:
                study_start_time = datetime(current_date.year, current_date.month, current_date.day, 19, 0)  # Evening study time (7:00 PM)
                study_end_time = study_start_time + timedelta(hours=study_hours)

            # Round study start and end times to the nearest hour or half-hour
            study_start_time = round_time(study_start_time)
            study_end_time = round_time(study_end_time)

            # Mark revision topics appropriately
            topic_label = topic
            if cycle_counter > 0:
                topic_label =  topic + "(Revision)"

            schedule[current_date.strftime('%Y-%m-%d')] = {
                'topic': topic_label,
                'start_time': study_start_time.strftime('%H:%M'),
                'end_time': study_end_time.strftime('%H:%M')
            }

            # Move to the next day
            current_date += timedelta(days=1)

            # Break if end date is reached
            if current_date > end_date:
                break

        cycle_counter += 1

    return schedule

def round_time(dt):
    """Round time to the nearest hour or half-hour"""
    dt += timedelta(minutes=15)  # Add 15 minutes to round up if the minute is greater than 30
    rounded = dt - timedelta(minutes=dt.minute % 30, seconds=dt.second, microseconds=dt.microsecond)
    return rounded




# Example Flask route to authenticate requests

@app.route('/dashboard_data/<userid>')
def dashboard_data(userid):

    user_ref = db.collection('users').document(userid)
    # Fetch user preferences and topics from Firestore
    user_doc = user_ref.get()
    
    print(user_doc)
    if not user_doc.exists:
        return jsonify({'error': 'User not found'}), 404
    data = user_doc.to_dict()
    name=data.get('name')
    print(name)
    schedule = data.get('schedule')
    preference = data.get('preferences')
    # Calculate progress in study
    total_study_hours = sum((end_time - start_time).total_seconds() / 3600
                            for date, details in schedule.items()
                            for start_time, end_time in [(datetime.strptime(details['start_time'], '%H:%M'), datetime.strptime(details['end_time'], '%H:%M'))])
    current_date = datetime.now()
    start_date=datetime.strptime(preference['startDate'], "%Y-%m-%d")
    end_date=datetime.strptime(preference['endDate'], "%Y-%m-%d")
    elapsed_days = (current_date - start_date).days
    hours_completed = 0
    for i in range(elapsed_days):
        date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        if date in schedule:
            start_time = datetime.strptime(schedule[date]['start_time'], '%H:%M')
            end_time = datetime.strptime(schedule[date]['end_time'], '%H:%M')
            hours_completed += (end_time - start_time).total_seconds() / 3600

    progress_percentage = (hours_completed / total_study_hours) * 100

    # Calculate number of days left
    days_left = (end_date - current_date).days

    # Get today's schedule
    today_schedule = schedule.get(current_date.strftime('%Y-%m-%d'), 'No study time today')
    try:
        topic = today_schedule['topic']
    except:
        topic = "No Topic for Today"
    video = get_top_videos(topic + "for JAM exam")
    print(video)


    return jsonify({
        'progress_percentage': progress_percentage,
        'days_left': days_left,
        'today_schedule': today_schedule,
        'today_video' : video,
        'name':name
    })


@app.route('/resource/<userid>', methods=['GET'])
def get_resource(userid):
    doc_id = userid  # Replace with the actual document ID

    doc_ref = db.collection('users').document(doc_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        topics = data.get('preferences', {}).get('topics', [])

        # Fetch top videos for each event
        topic_videos = {}
        for event in topics:
            videos = get_top_videos(event+"for JAM exam")
            topic_videos[event] = videos  # Take only the first two videos for each event
        print(topic_videos)
        return jsonify({'event_videos': topic_videos})
    else:
        return jsonify({'error': 'Document not found'})


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
    
    
    schedule = calculate_schedule(preferences)
    if schedule:
            user_ref.update({"schedule": schedule})
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
@app.route("/journal/<userid>/<index>", methods=["PUT", "DELETE"])
def handle_journal_update(userid, index):
    index = int(index)  # Convert index to integer
    if request.method == "PUT":
        # Get updated journal content from request body
        updated_content = request.json

        # Update journal content in the database
        user_ref = db.collection("users").document(userid)
        user_data = user_ref.get()

        if user_data.exists:
            # User exists, update journal content
            journal_data = user_data.to_dict().get("journal", [])
            if index < len(journal_data):
                # Update journal entry at the specified index
                journal_data[index] = updated_content
                user_ref.update({"journal": journal_data})
                return jsonify(updated_content)
            else:
                return jsonify({"error": "Index out of range"})
        else:
            return jsonify({"error": "User does not exist"})

    elif request.method == "DELETE":
        # Delete journal entry from the database
        user_ref = db.collection("users").document(userid)
        user_data = user_ref.get()

        if user_data.exists:
            # User exists, delete journal entry
            journal_data = user_data.to_dict().get("journal", [])
            if index < len(journal_data):
                # Remove journal entry at the specified index
                del journal_data[index]
                user_ref.update({"journal": journal_data})
                return jsonify({"message": "Journal entry deleted successfully"})
            else:
                return jsonify({"error": "Index out of range"})
        else:
            return jsonify({"error": "User does not exist"})


@app.route("/preference/<userid>", methods=["GET", "POST"])
def preference(userid):
    user_ref = db.collection('users').document(userid)
    
    if request.method == "GET":
        # Check if user exists in Firestore
        user_doc = user_ref.get()
        print(user_doc)
        if user_doc.exists:
            # Check if preferences exist
            preferences = user_doc.to_dict().get('preferences')
            return jsonify(preferences) if preferences else jsonify(None)
        else:
            # If user does not exist, create a new document with empty preferences
            user_ref.update({'preferences': {}})
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
        user_ref.update({'preferences': data})
        return jsonify(data)
@app.route('/profile/<userid>', methods=['GET'])
def get_profile(userid):

        # Fetch user data from Firestore
    user_ref = db.collection('users').document(userid)
    user_data = user_ref.get()
    print(user_data)

    if user_data.exists:
        print("aaa")
        name=user_data.get('name')
        email=user_data.get('email')
        try:
            image=user_data.get('image')
        except:
            image=None
        user_details={'name':name,'email':email,"image":image}
        return jsonify(user_details), 200
    else:
        return jsonify({'error': 'User not found'}), 404

@app.route('/upload_image/<userid>', methods=['POST'])
def set_image(userid):
    if 'image' in request.files:
            file = request.files['image']
            if file:
                # Save the uploaded PDF file to a temporary location
                file_url=upload_file_to_firestore(file)
                user_ref = db.collection('users').document(userid)
                user_ref.update({'image':file_url})
                return jsonify("image uploaded")

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
