# CampusConnect – Digital College Notice Board

A full stack web app that brings college **events, academic notices and announcements** into one place. Students can search and register for events, organizations can publish their own notices, and organizers can mark attendance by scanning QR codes.

Built with **Flask, MySQL, HTML, CSS and JavaScript**.

---

## Features

### For students
- Register and log in with USN and password
- Browse and search events, academic notices and announcements
- **Register for events**. Duplicate registrations are blocked
- Track registration status: **Registered**, **Attended** or **Cancelled**
- **Student dashboard**: My Registrations, Upcoming Events and Bookmarked Events
- **Bookmark** events to find them later
- **Unique QR pass** for every registration, with a backup code
- **Notifications** (bell icon): registration confirmation, cancellation, attendance marked, and event reminders (events today or within 2 days)

### For organizations (clubs, departments)
- Register and wait for Super Admin approval
- Own dashboard to **create, edit and delete only their own** events, academic notices and announcements
- See how many students registered and attended each event
- **QR attendance**: scan a student's QR code (phone camera, in-page scanner, or paste the code) and mark them present. Each code works only once.

### For the Super Admin
- Publish, edit and delete any notice
- View attendance for any event

---

## Tech Stack

| Part | Technology |
|---|---|
| Backend | Python, Flask |
| Database | MySQL |
| Frontend | HTML, CSS, JavaScript, Jinja templates |
| QR codes | `qrcode` + Pillow |
| Other | `mysql-connector-python`, `python-dotenv` |

---

## Security Basics

- Passwords are stored as hashes, never as plain text
- Every database query uses parameters (protects against SQL injection)
- Organizations can only change rows that belong to them (checked on the server)
- QR codes use long random tokens and work only once
- Only PDF files are accepted for uploads (10 MB limit)
- Secrets are kept in a `.env` file that is not uploaded to GitHub

---

## Project Structure

```
CampusConnect/
├── app.py              # Flask routes and logic
├── db_setup.py         # Creates new tables/columns (safe to run again)
├── database.sql        # Full database schema
├── requirements.txt    # Python packages
├── .env.example        # Example settings (copy to .env)
├── templates/          # HTML pages (Jinja)
├── static/
│   ├── css/            # Styles
│   └── js/             # Scripts
└── uploads/            # Uploaded PDF notices (not on GitHub)
```

---

## How to Run

### 1. Requirements
- Python 3.10 or newer
- MySQL Server

### 2. Get the code
```bash
git clone https://github.com/vanigm2007-dotcom/campusconnect-notice-board.git
cd campusconnect-notice-board
```

### 3. Install packages
```bash
pip install -r requirements.txt
```

### 4. Create the database
In MySQL, run:
```sql
CREATE DATABASE campusconnect;
CREATE USER 'campusconnect_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX
ON campusconnect.* TO 'campusconnect_user'@'localhost';
FLUSH PRIVILEGES;
```
Then load the tables by running `database.sql`.

### 5. Add your settings
Copy `.env.example` to `.env` and fill it in:
```
DB_HOST=localhost
DB_USER=campusconnect_user
DB_PASSWORD=your_password
DB_NAME=campusconnect

SECRET_KEY=any-long-random-text

ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_admin_password
```

### 6. Start the app
```bash
python app.py
```
Open **http://127.0.0.1:5000** in your browser.

### 7. Approve an organization
After an organization registers, approve it in MySQL:
```sql
UPDATE organization_admins SET status='approved' WHERE email='club@example.com';
```

### Testing QR codes with a phone (optional)
A phone cannot open `127.0.0.1`. Add your computer's Wi-Fi address to `.env`, for example:
```
PUBLIC_BASE_URL=http://192.168.1.5:5000
```
and run the app with `flask run --host=0.0.0.0` (the phone must be on the same Wi-Fi).

---

## Database Tables

`students`, `organization_admins`, `events`, `academic_notices`, `announcements`, `event_registrations`, `event_bookmarks`, `notifications`

---

## Future Improvements

- Add to Google Calendar / `.ics` download for events
- Email notifications
- Page for the Super Admin to approve organizations
- Better mobile layout
- CSRF protection and login attempt limits before public deployment

---

## Author

**Vani G M**
B.E. Computer Science and Engineering, B.M.S. College of Engineering, Bengaluru

[GitHub](https://github.com/vanigm2007-dotcom) · [LinkedIn](https://linkedin.com/in/vani-g-m-157362409)
