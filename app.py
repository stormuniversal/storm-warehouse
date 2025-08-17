from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional
from flask_wtf import FlaskForm
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, text as sqltext
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import os

# --- Config ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey-change-me')
# Data directory (Render persistent disk mounts to /data)
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- DB ---
Base = declarative_base()
engine = create_engine(f"sqlite:///{os.path.join(DATA_DIR, 'warehouse.db')}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# --- Models ---
class User(Base, UserMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(20), nullable=False)  # applicant, stockman, manager, admin

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

class Ticket(Base):
    __tablename__ = 'tickets'
    id = Column(Integer, primary_key=True)
    project_name = Column(String(120), nullable=False)
    applicant_name = Column(String(120), nullable=False)
    applicant_phone = Column(String(40), nullable=False)
    status = Column(String(30), default='Новая')  # only stockman can change
    created_at = Column(DateTime, default=datetime.utcnow)
    pickup_at = Column(DateTime, nullable=True)  # дата/время забора материалов
    pickup_recipient = Column(String(120), nullable=True)  # кто получил материалы
    pickup_proof_path = Column(String(255), nullable=True)  # фото/подпись подтверждения
    closed_at = Column(DateTime, nullable=True)  # дата/время закрытия заявки
    created_by_id = Column(Integer, ForeignKey('users.id'))
    created_by = relationship('User')

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('tickets.id'))
    author_id = Column(Integer, ForeignKey('users.id'))
    text = Column(Text, nullable=True)
    photo_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship('Ticket', backref='comments')
    author = relationship('User')

Base.metadata.create_all(engine)

# Lightweight migration if DB уже существует без новых колонок
with engine.connect() as conn:
    info = conn.execute(sqltext("PRAGMA table_info(tickets)")).fetchall()
    cols = {row[1] for row in info}
    if 'pickup_at' not in cols:
        conn.execute(sqltext("ALTER TABLE tickets ADD COLUMN pickup_at DATETIME"))
    if 'closed_at' not in cols:
        conn.execute(sqltext("ALTER TABLE tickets ADD COLUMN closed_at DATETIME"))

# Seed default users if not exist
def seed():
    if db.query(User).count() == 0:
        users = [
            ('admin', 'admin123', 'admin'),
            ('applicant1', 'test123', 'applicant'),
            ('stockman1', 'test123', 'stockman'),
            ('manager1', 'test123', 'manager'),
        ]
        for u,p,r in users:
            db.add(User(username=u, password_hash=generate_password_hash(p), role=r))
        db.commit()
seed()

# --- Forms ---
class LoginForm(FlaskForm):
    username = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

class TicketForm(FlaskForm):
    project_name = StringField('Наименование проекта', validators=[DataRequired(), Length(max=120)])
    applicant_name = StringField('Имя и фамилия заявителя', validators=[DataRequired(), Length(max=120)])
    applicant_phone = StringField('Телефон', validators=[DataRequired(), Length(max=40)])
    description = TextAreaField('Комментарий', validators=[Optional()])
    submit = SubmitField('Создать заявку')

class CommentForm(FlaskForm):
    text = TextAreaField('Комментарий', validators=[Optional()])
    submit = SubmitField('Добавить')

class StatusForm(FlaskForm):
    status = SelectField('Статус', choices=[
        ('Новая','Новая'),
        ('В работе','В работе'),
        ('Ожидает материалов','Ожидает материалов'),
        ('Готово к выдаче','Готово к выдаче'),
        ('Материал забран','Материал забран'),
        ('Закрыта','Закрыта'),
    ])
    submit = SubmitField('Обновить статус')

# --- Login manager ---
@login_manager.user_loader
def load_user(user_id):
    return db.get(User, int(user_id))

# --- Role helper ---
def require_role(*roles):
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('Нет доступа для вашей роли', 'error')
                return redirect(url_for('dashboard'))
            return func(*args, **kwargs)
        return wrapper
    return decorator

# --- Routes ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.query(User).filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Applicants see only their tickets, others see all
    if current_user.role == 'applicant':
        tickets = db.query(Ticket).filter_by(created_by_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    else:
        tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    return render_template('dashboard.html', tickets=tickets)

@app.route('/tickets/new', methods=['GET','POST'])
@login_required
def new_ticket():
    if current_user.role not in ('applicant','admin','manager'):
        flash('Создавать заявки может только заявитель/менеджер/администратор', 'error')
        return redirect(url_for('dashboard'))
    form = TicketForm()
    if form.validate_on_submit():
        t = Ticket(
            project_name=form.project_name.data,
            applicant_name=form.applicant_name.data,
            applicant_phone=form.applicant_phone.data,
            status='Новая',
            created_by=current_user
        )
        db.add(t)
        db.commit()
        if form.description.data:
            c = Comment(ticket=t, author=current_user, text=form.description.data)
            db.add(c)
            db.commit()
        flash('Заявка создана', 'success')
        return redirect(url_for('ticket_detail', ticket_id=t.id))
    return render_template('ticket_new.html', form=form)

@app.route('/tickets/<int:ticket_id>', methods=['GET','POST'])
@login_required
def ticket_detail(ticket_id):
    t = db.get(Ticket, ticket_id)
    if not t:
        flash('Заявка не найдена', 'error')
        return redirect(url_for('dashboard'))
    comment_form = CommentForm()
    status_form = StatusForm()
    # Comments
    if 'add_comment' in request.form and comment_form.validate_on_submit():
        photo = None
        if 'photo' in request.files and request.files['photo'].filename:
            f = request.files['photo']
            fname = secure_filename(f.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{datetime.utcnow().timestamp()}_{fname}")
            f.save(save_path)
            photo = os.path.basename(save_path)
        c = Comment(ticket=t, author=current_user, text=comment_form.text.data or '', photo_path=photo)
        db.add(c)
        db.commit()
        flash('Комментарий добавлен', 'success')
        return redirect(url_for('ticket_detail', ticket_id=t.id))
    # Status update (stockman only)
    if 'update_status' in request.form and status_form.validate_on_submit():
        if current_user.role != 'stockman' and current_user.role != 'admin':
            flash('Менять статус может только складчик или администратор', 'error')
            return redirect(url_for('ticket_detail', ticket_id=t.id))
        new_status = status_form.status.data
        if new_status == 'Материал забран':
            t.status = 'Закрыта'  # закрываем заявку
            t.pickup_at = datetime.utcnow()  # фиксируем дату/время забора
            t.closed_at = t.pickup_at        # фиксируем дату/время закрытия
        else:
            t.status = new_status
            if new_status == 'Закрыта' and not t.closed_at:
                t.closed_at = datetime.utcnow()
        db.commit()
        flash('Статус обновлён', 'success')
        return redirect(url_for('ticket_detail', ticket_id=t.id))
    return render_template('ticket_detail.html', t=t, comment_form=comment_form, status_form=status_form)

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Admin: user list (very basic)
@app.route('/admin/users')
@login_required
@require_role('admin')
def admin_users():
    users = db.query(User).order_by(User.username).all()
    return render_template('admin_users.html', users=users)

@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', message='Доступ запрещён'), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
