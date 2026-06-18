"""Generate a sample question-bank PDF that mimics the GS Score 'Map Based
Questions' layout: a QUESTIONS section, then a SEPARATE answer-key section.
Uses real questions from that book + one non-place question to prove the
map-relevant filter drops it."""
import fitz

QUESTIONS_PAGE_1 = (
    "MAP BASED QUESTIONS\nTime Allowed: 2 hours    Maximum Marks: 100\n\n"
    "1. Which of the following statement is/are correct regarding Makassar Strait?\n"
    "   1. It separates Borneo (Kalimantan) and Celebes Island.\n"
    "   2. It connects Celebes Sea with Java Sea.\n"
    "   (a) 1 only   (b) 2 only   (c) Both 1 and 2   (d) Neither 1 nor 2\n\n"
    "2. Which of the following lakes are correctly matched with the respective "
    "countries they are situated in?\n"
    "   1. Lake Baikal: Russia   2. Lake Akan: Indonesia\n"
    "   3. Lake Matano: Japan    4. Qinghai Lake: China\n"
    "   (a) 1 and 4 only   (b) 2 and 3 only   (c) 1, 2 and 3 only   (d) 2, 3 and 4 only\n\n"
    "3. Which of the following seas is/are not a part of Pacific Ocean?\n"
    "   1. Sulu Sea   2. Arafura Sea   3. Kara Sea   4. Laptev Sea\n"
    "   (a) 1 and 3 only   (b) 2 and 4 only   (c) 1 and 2 only   (d) 3 and 4 only\n"
)

QUESTIONS_PAGE_2 = (
    "16. Aral Sea is enclosed between which of the following two countries?\n"
    "   (a) Azerbaijan and Kazakhstan   (b) Uzbekistan and Azerbaijan\n"
    "   (c) Uzbekistan and Kazakhstan   (d) Turkmenistan and Kazakhstan\n\n"
    "96. Consider the following Tiger Reserves:\n"
    "   1. Melghat Tiger Reserve   2. Mukundra Hills Tiger Reserve\n"
    "   3. Pilibhit Tiger Reserve  4. Valmiki Tiger Reserve\n"
    "   Arrange the above in a north to south direction.\n"
    "   (a) 3, 4, 2, 1   (b) 3, 2, 4, 1   (c) 1, 4, 2, 3   (d) 4, 3, 1, 2\n\n"
    "101. What is the SI unit of force?\n"
    "   (a) Joule   (b) Newton   (c) Watt   (d) Pascal\n"
)

ANSWER_PAGE = (
    "ANSWER HINTS\n\n"
    "1. Correct Option: (c)\n"
    "2. Correct Option: (a)\n"
    "3. Correct Option: (d)\n"
    "16. Correct Option: (c)\n"
    "96. Correct Option: (a)\n"
    "101. Correct Option: (b)\n"
)

doc = fitz.open()
for text in (QUESTIONS_PAGE_1, QUESTIONS_PAGE_2, ANSWER_PAGE):
    page = doc.new_page()
    page.insert_text((54, 60), text, fontsize=10)
doc.save("data/books/test_qbank.pdf")
print("wrote data/books/test_qbank.pdf  pages:", doc.page_count)
