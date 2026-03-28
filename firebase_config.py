import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
from dotenv import load_dotenv
from unittest.mock import MagicMock

load_dotenv()

# Mock storage for development
class MockFirestore:
    def __init__(self):
        self._data = {}
    
    def collection(self, name):
        return MockCollection(name, self._data)

class MockCollection:
    def __init__(self, name, data):
        self.name = name
        self._data = data
        if name not in self._data:
            self._data[name] = {}
    
    def document(self, doc_id):
        return MockDocument(self.name, doc_id, self._data[self.name])
    
    def where(self, field, op, value):
        return self
    
    def stream(self):
        return [MockDocSnapshot(doc_id, data) for doc_id, data in self._data[self.name].items()]

class MockDocument:
    def __init__(self, collection, doc_id, data):
        self.collection = collection
        self.doc_id = doc_id
        self._data = data
    
    def set(self, data):
        self._data[self.doc_id] = data
    
    def get(self):
        return MockDocSnapshot(self.doc_id, self._data.get(self.doc_id))
    
    def delete(self):
        if self.doc_id in self._data:
            del self._data[self.doc_id]

class MockDocSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
    
    def to_dict(self):
        return self._data

class MockStorageBucket:
    def blob(self, path):
        return MockBlob(path)

class MockBlob:
    def __init__(self, path):
        self.path = path
        self.public_url = f"https://storage.mock/items/{path}"
    
    def upload_from_string(self, content, content_type=None):
        pass
    
    def make_public(self):
        pass

# Initialize Firebase Admin SDK
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            # Try to initialize with credentials if available
            cred_path = os.path.join(os.path.dirname(__file__), 'firebase-credentials.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET', 'your-project.appspot.com')
                })
            else:
                # Mock initialization for development
                print("Firebase credentials not found, using mock storage")
                return True
        except Exception as e:
            print(f"Firebase initialization: {e}")
            return True
    return False

def get_firestore_client():
    is_mock = initialize_firebase()
    if is_mock:
        return MockFirestore()
    return firestore.client()

def get_storage_bucket():
    is_mock = initialize_firebase()
    if is_mock:
        return MockStorageBucket()
    return storage.bucket()