import sys
from passlib.context import CryptContext
from dotenv import load_dotenv
load_dotenv()
from supabase_client import get_supabase

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def add_user(username, password):
    supabase = get_supabase()
    
    # Hash password
    hashed_pw = pwd_context.hash(password)
    
    try:
        res = supabase.table("staff_users").insert({
            "username": username,
            "password_hash": hashed_pw
        }).execute()
        print(f"Success! Added user: {username}")
    except Exception as e:
        print(f"Error adding user {username}: {e}")

if __name__ == "__main__":
    if len(sys.argv) == 3:
        add_user(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python add_user.py <username> <password>")
