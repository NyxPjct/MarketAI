import os
os.environ.setdefault('DATABASE_URL','sqlite:///./test-marketai-cloud.db')
os.environ.setdefault('JWT_SECRET','test-secret-abcdefghijklmnopqrstuvwxyz-1234567890')
os.environ.setdefault('ADMIN_API_KEY','admin-test')
os.environ.setdefault('ADMIN_PANEL_ENABLED','true')
