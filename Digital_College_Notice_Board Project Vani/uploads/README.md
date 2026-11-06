# Digital College Notice Board – CampusConnect

## Project Description

CampusConnect is a web-based college notice board that helps students view college events, academic notices, and important announcements in one place.

## Technologies Used

* Python
* Flask
* MySQL
* HTML
* CSS
* JavaScript

## Main Features

* College home page
* View upcoming events
* View individual event details
* View academic notices
* View college announcements
* MySQL database connectivity
* QR code generation support

## Database

Database name: `campusconnect`

Tables:

* events
* academic_notices
* announcements
* admins

## Installation

Install the required packages:

```bash
python -m pip install -r requirements.txt
```

Execute `database.sql` in MySQL Workbench.

Configure the database password in the `DB_PASSWORD` environment variable.

Run the application:

```bash
python app.py
```

Open the browser:

```text
http://127.0.0.1:5000
```

## Project Objective

To provide students with easy and centralized access to important college information through a digital platform.

## Project Type

Academic Group Project
