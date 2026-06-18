"""Generate a tiny sample PYQ paper PDF (mixed subjects + answer key) for testing."""
import fitz

QUESTIONS = (
    "UPSC Civil Services Preliminary Examination 2023 - General Studies Paper I\n\n"
    "1. The Tropic of Cancer passes through which of the following Indian states?\n"
    "   (a) Rajasthan   (b) Kerala   (c) Punjab   (d) Tamil Nadu\n\n"
    "2. Which Article of the Indian Constitution deals with the Right to Equality?\n"
    "   (a) Article 12   (b) Article 14   (c) Article 19   (d) Article 21\n\n"
    "3. What is the SI unit of force?\n"
    "   (a) Joule   (b) Newton   (c) Watt   (d) Pascal\n\n"
    "4. The river Godavari originates in which state?\n"
    "   (a) Maharashtra   (b) Karnataka   (c) Telangana   (d) Odisha\n\n"
    "5. Who was the first Governor-General of independent India?\n"
    "   (a) C. Rajagopalachari   (b) Lord Mountbatten   (c) Rajendra Prasad   (d) Nehru\n"
)

ANSWER_KEY = (
    "ANSWER KEY\n\n"
    "1. (a) Rajasthan\n"
    "2. (b) Article 14\n"
    "3. (b) Newton\n"
    "4. (a) Maharashtra\n"
    "5. (b) Lord Mountbatten\n"
)

doc = fitz.open()
for text in (QUESTIONS, ANSWER_KEY):
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
doc.save("data/sample/test_pyq.pdf")
print("wrote data/sample/test_pyq.pdf  pages:", doc.page_count)
