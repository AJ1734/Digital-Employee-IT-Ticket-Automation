"""
seed.py – Re-seed the databases from scratch (standalone helper).
"""
from database import init_db, seed_db
from rag_setup import init_chroma

if __name__ == "__main__":
    print("Initialising SQLite…")
    init_db()
    seed_db()
    print("SQLite seeded.")
    print("Initialising ChromaDB…")
    init_chroma()
    print("Done.")
