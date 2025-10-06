from app import app, db, Player
import utils

# Use the Flask app context so db.session works
with app.app_context():
    # Ensure the table exists
    db.create_all()

    # Add some rows
    player1 = Player(rank=1, name="Cameron Ward", team="Miami Hurricanes")
    player2 = Player(rank=2, name="Travis Hunter", team="Colorado Buffaloes")

    db.session.add_all([player1, player2])
    db.session.commit()

    print("Seeded database with players!")
