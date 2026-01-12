"""
Edibes Leltár - Fő alkalmazás indító
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Fejlesztési mód - 0.0.0.0 minden interface-en figyel (helyi hálózat)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
