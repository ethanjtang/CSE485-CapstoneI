from flask import Flask, request, jsonify
import google.generativeai as genai
import os
from flask_cors import CORS
from langdetect import detect
from dotenv import load_dotenv
import time
import subprocess

# Load the .env.local file to access the decryption password
load_dotenv(".env.local")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Function to decrypt the .env file
def decrypt_env_file(encrypted_file=".env.enc", decrypted_file=".env"):
    # Retrieve the decryption password from the environment variables loaded from .env.local
    decryption_password = os.environ.get("DECRYPTION_PASSWORD")
   
    if not decryption_password:
        print("Decryption password not found in .env.local.")
        return False


    # Decrypt the .env.enc file using openssl and output to .env
    try:
        subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-d", "-pbkdf2",
             "-in", encrypted_file, "-out", decrypted_file, "-pass", f"pass:{decryption_password}"],
            check=True
        )
        print("Decryption successful")
    except subprocess.CalledProcessError:
        print("Decryption failed")
        return False
    return True

# Decrypt and load environment variables
if decrypt_env_file():
    load_dotenv(".env")  # Load variables from the decrypted .env file
    os.remove(".env")  # Remove the temporary .env file after loading
else:
    raise Exception("Failed to decrypt .env file.")

# Retrieve API keys from the environment variables
API_KEYS = [
    os.environ.get("GENAI_API_KEY_1"),
    os.environ.get("GENAI_API_KEY_2"),
]

# Initial API key index
current_api_key_index = 0

# Function to get the current API key
def get_current_api_key():
    return API_KEYS[current_api_key_index]

# Function to switch to the next API key
def switch_api_key():
    global current_api_key_index
    current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)

# Configure the Generative AI model
def configure_genai():
    genai.configure(api_key=get_current_api_key())
    return genai.GenerativeModel("gemini-1.5-flash")

# Define a route for the chatbot interaction
chat_history = [
    {"role": "user", "parts": "Hello, you are a chatbot designed to help users with real-estate related questions."},
    {"role": "model", "parts": "Hello! How can I help you with real estate?"}  # Shortened response
]

def detect_language(text):
    try:
        return detect(text)
    except:
        return 'en'  # Default to English

@app.route('/api/chat', methods=['POST'])
def chat_with_bot():
    global chat_history
    data = request.get_json()
    user_question = data.get('question') + " Please respond in no more than 200 words. Output in sentences."

    if not user_question:
        return jsonify({"error": "Question is required"}), 400

    # Detect language
    language = detect_language(user_question)

    # If the detected language is not English, include it in the system instructions
    if language != 'en':
        chat_history.insert(0, {"role": "system", "parts": f"Respond in {language}."})

    # Append the user's question to the chat history
    chat_history.append({"role": "user", "parts": user_question})

    try:
        # Create a new chat session
        model = configure_genai()  # Reconfigure the model with the current API key
        chat_session = model.start_chat(history=chat_history)

        # Generate a response from the model using send_message
        response = chat_session.send_message(user_question)
        
    except Exception as e:
        # If rate limit error (or other error), switch the API key and retry
        if 'rate limit' in str(e).lower():  # You can refine this check depending on the error message
            print(f"Rate limit reached for API Key {get_current_api_key()}. Switching to the next key.")
            switch_api_key()  # Switch to the next API key
            time.sleep(2)  # Optional: Wait a little before retrying
            return chat_with_bot()  # Retry with the new API key
        else:
            print("Error calling chat model:", str(e))
            return jsonify({"error": "Failed to communicate with the model."}), 500

    response_text = response.text if hasattr(response, 'text') else "No response text available"

    # Append the model's response to the chat history
    chat_history.append({"role": "model", "parts": response_text})

    return jsonify({"response": response_text})


# Run the Flask app
if __name__ == '__main__':
    app.run(debug=True)