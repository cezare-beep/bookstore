from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy_serializer import SerializerMixin


Base = declarative_base()


class Author(Base, SerializerMixin):
    __tablename__ = 'authors'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    photo = Column(String(100), nullable=False)
    wiki = Column(String(100), nullable=False)


class Book(Base, SerializerMixin):
    __tablename__ = 'books'
    id = Column(Integer, primary_key=True)
    book = Column(String(100), nullable=False)
    description = Column(String(1000), nullable=False)
    icon_book = Column(String(100), nullable=False)
    author_id = Column(Integer, ForeignKey('authors.id'))
    author = relationship("Author", backref="books")


class User(Base, SerializerMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), index=True, unique=True)
    email = Column(String(120), index=True, unique=True)
    password_hash = Column(String(128))

    def __repr__(self):
        return '<User {}>'.format(self.name)

