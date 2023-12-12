from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Sequence, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session, scoped_session, close_all_sessions
from sqlalchemy.pool import StaticPool
from databases import Database
from pydantic import BaseModel
from contextlib import contextmanager
import requests
from typing import List
import os

DATABASE_URL = "sqlite:///./test.db"
#The purpose of the code below is to ensure that we dont face issues in multi-threaded environment/ handling multi-threading and ensure thread safety

# Establishing Database connection based on the database URL with StaticPool
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)

# This event listener will emit a signal when a connection is first established
# This is to ensure the SQLite database is created within the same thread as the connection
@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    connection_record.info["pid"] = None

# This event listener will check if the connection is still valid before using it
@event.listens_for(engine, "checkout")
def checkout(dbapi_connection, connection_record, connection_proxy):
    pid = os.getpid() # Get the process ID of the current process
    # Check if the stored process ID in connection_record.info is None or different from the current process ID
    if connection_record.info["pid"] is None or connection_record.info["pid"] != pid:
        connection_record.info["pid"] = pid # Update the stored process ID with the current process ID

#Creating a new database session object for each thread/manages database session in thread safe manner
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False))

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, Sequence("user_id_seq"), primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

#Code to create a database table
Base.metadata.create_all(bind=engine)

# pydantic model to validate and serialize the incoming data(request payloads)
class UserCreate(BaseModel):
    username: str
    password: str

# pydantic model to validate and serialize the response data(response payloads)
class UserResponse(BaseModel):
    id: int
    username: str

app = FastAPI()

# Dependency to get the database session(manages and shares resources across multiple endpionts/routes)
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    finally:
        db.close()

# Create a new user
@app.post("/create_user")
async def create_user(user_create: UserCreate, db: Session = Depends(get_db)):
    # Check if the username already exists
    existing_user = db.query(User).filter(User.username == user_create.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    # If the username is unique, proceed with creating the user
    with db:
        user = User(username=user_create.username, password=user_create.password)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# Route to get all users(fetching users from the database)
@app.get("/get_users", response_model=list[UserResponse])
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

# Deleting a user from the database
@app.delete("/delete_user/{user_id}", response_model=UserResponse)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    # Query the database to get the user with the specified user_id
    user = db.query(User).filter(User.id == user_id).first()

    # Check if the user exists
    if user:
        # If the user exists, proceed with deletion
        with db:
            db.delete(user)  # Delete the user from the database
            db.commit()      # Commit the changes to the database

        # Return the deleted user as a response
        return user
    else:
        # If the user does not exist, raise an HTTPException with a 404 status code
        raise HTTPException(status_code=404, detail="User not found")


    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
