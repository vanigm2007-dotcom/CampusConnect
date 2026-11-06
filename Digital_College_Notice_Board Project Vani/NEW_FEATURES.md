# New features (how to set up)

1. Install the new package:   pip install -r requirements.txt
2. Run the app:               python app.py
   (The new tables/columns are created automatically on start.
    You can also run `python db_setup.py` by hand.)

## Approve an organization (Super Admin step)
UPDATE organization_admins SET status='approved' WHERE email='club@example.com';

## Test QR scanning from a phone (optional)
Add this line to .env, using your computer's Wi-Fi address:
PUBLIC_BASE_URL=http://192.168.1.5:5000
and start the app with:  flask run --host=0.0.0.0   (same Wi-Fi needed)
