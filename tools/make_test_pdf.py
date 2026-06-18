"""Generate a tiny 3-page geography PDF for testing the extractor."""
import fitz

PAGES = [
    "Chapter 1: Rivers of India\n\n"
    "The Ganga is the longest river in India. It flows through Madhya Pradesh "
    "and Maharashtra before reaching the sea. The river supports millions.",
    "Chapter 2: States\n\n"
    "Rajasthan is the largest state in India by area. Gujarat lies to its "
    "south-west. Maharashtra is India's financial heartland with Mumbai.",
    "Chapter 3: Mountains\n\n"
    "The Himalaya range forms India's northern boundary and feeds many rivers "
    "including the Ganga.",
]

doc = fitz.open()
for t in PAGES:
    page = doc.new_page()
    page.insert_text((72, 72), t, fontsize=11)
doc.save("data/sample/test_book.pdf")
print("wrote data/sample/test_book.pdf  pages:", doc.page_count)
