from contextlib import contextmanager
from functools import wraps

import requests
import os.path
from bs4 import BeautifulSoup
from flask import *
from sqlalchemy import create_engine, exc
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import sessionmaker
from db_setup import Book, Author, Base
from flask_restful import abort, Api, Resource
from flask_wtf import FlaskForm
from flask_login import *
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo
from config import Config
from werkzeug.urls import url_parse
from models import User

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config.from_object(Config)
login = LoginManager(app)
login.login_view = 'login'
db = SQLAlchemy(app)
api = Api(app)

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "books.db")
engine = create_engine('sqlite:///{}?check_same_thread=False'.format(db_path))
Base.metadata.bind = engine
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def with_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with get_db() as db:
            return func(db, *args, **kwargs)

    return wrapper


@app.route('/')
@with_session
def index(db):
    query = db.query(Book, Author)
    query = query.join(Author, Book.author_id == Author.id)
    query_all = query.all()
    query_list = []
    for book, author in query_all:
        books_dic = book.to_dict(only=('id', 'book', 'description', 'icon_book'))
        authors_dic = author.to_dict(only=('name', 'photo'))
        query_dic = books_dic | authors_dic
        query_list.append(query_dic)
    return render_template('index.html', books=query_list)


@app.route('/api/books', methods=['POST'])
@with_session
def create_book(db):
    if not request.json:
        return jsonify({'error': 'Empty request'})
    elif not all(key in request.json for key in
                 ['book']):
        return jsonify({'error': 'Bad request'})
    author = Author(
        name=request.json['name'],
        photo=request.json['photo'],
        wiki=request.json['wiki']
    )
    author_id = db.query(Author.id).filter(Author.name == request.json['name'])
    book = Book(
        book=request.json['book'],
        description=request.json['description'],
        icon_book=request.json['icon_book'],
        author_id=author_id
    )
    db.add_all([author, book])
    db.commit()
    return jsonify({'success': 'OK'})


@app.route('/authors')
@with_session
def get_authors(db):
    authors = db.query(Author).distinct(Author.name).all()
    return render_template('authors.html', authors=authors)


@app.route('/authors/<int:author_id>/about')
@with_session
def authors_wiki(db, author_id):
    author = db.query(Author).filter_by(id=author_id).one()
    url = db.query(Author.wiki).filter_by(id=author_id).one()[0]
    response = requests.get(url)
    doc = BeautifulSoup(response.text, 'lxml')
    intro = doc.body.find_all('p')[2].text
    labels = doc.body.find_all('th', attrs={'class': 'infobox-label'})
    labels_list = [x.text for x in labels]
    data = doc.body.find_all('td', attrs={'class': 'infobox-data'})
    data_list = [x.text for x in data]
    return render_template('about.html', author=author, about=intro, data=data_list, labels=labels_list)


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


@login.user_loader
@with_session
def load_user(db, id):
    return db.query(User).get(int(id))


@app.route('/sign_in', methods=['GET', 'POST'])
@with_session
def login(db):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.query(User).filter_by(name=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('sign_in.html', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        with get_db() as db:
            user = db.query(User).filter_by(name=username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        with get_db() as db:
            user = db.query(User).filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('Please use a different email address.')


def redirect_to_index_if_authenticated(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        return func(*args, **kwargs)

    return wrapper


@app.route('/register', methods=['GET', 'POST'])
@redirect_to_index_if_authenticated
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(name=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


def abort_if_book_not_found(db, book_id):
    book = db.query(Book).get(book_id)
    if not book:
        abort(404, message="Book {book_id} not found".format(book_id))


class BookResource(Resource):
    @with_session
    def get(self, db, book_id):
        abort_if_book_not_found(db, book_id)
        book = db.query(Book).get(book_id)
        return jsonify(
            book.to_dict(only=('id', 'book'))
        )


@app.route('/book/<int:book_id>/<string:filename>', methods=['GET'])
@with_session
def get_book(db, book_id, filename):
    book = db.query(Book).filter_by(id=book_id).one()
    return render_template('book.html', book=book, value=filename)


@app.route('/search/', methods=['GET'])
@with_session
def search_book(db):
    try:
        book_name = request.args.get('book')
        books = db.query(Book).filter(Book.book.ilike("%{}%".format(book_name))).all()
        return render_template('search.html', books=books)
    except exc.NoResultFound:
        return render_template('search.html')


UPLOAD_FOLDER = 'static/files/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Функция для добавление книги
# @app.route('/uploadfile', methods=['GET', 'POST'])
# def upload_file():
#     if request.method == 'POST':
#         if 'file' not in request.files:
#             print('no file')
#             return redirect(request.url)
#         file = request.files['file']
#         if file.filename == '':
#             print('no filename')
#             return redirect(request.url)
#         else:
#             filename = secure_filename(file.filename)
#             file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#             print("saved file successfully")
#             return redirect(url_for(get_book) + filename)
#     return render_template('upload_file.html')


@app.route('/return-file/<filename>')
def return_files(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        return send_file(file_path, as_attachment=True, download_name='')
    except FileNotFoundError:
        return 'Book not found! We are sorry!'


api.add_resource(BookResource, '/book/<int:book_id>')
