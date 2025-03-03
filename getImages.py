# script to get images of puzzles from https://lidraughts.org/training/frisian/ for automatically creating videos
import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options as ChromeOptions
from PIL import Image
import io
import time

# start selemium
options = ChromeOptions()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)
driver.get("https://lidraughts.org/training/frisian/")
# 1762 for 1080
# 1650 for 998
driver.set_window_size(1650, 1650)
driver.implicitly_wait(0.5)
board = driver.find_element(By.CLASS_NAME, "main-board")
# click view solution button after it is visible
# wait for the button to be visible
view_solution_button = driver.find_element(By.CLASS_NAME, "view_solution")
wait = WebDriverWait(driver, 10)
wait.until(lambda _: view_solution_button.is_displayed())
view_solution_button.click()
time.sleep(1)

# for all <move class ... </move> or <move p ... </move> in <div class=tview2>
moveview_element = driver.find_element(By.CLASS_NAME, "tview2")
# subelements
i = 0
framenumber = 0
frames_per_move = 10
images = []
for move in moveview_element.find_elements(By.TAG_NAME, "move"):
    # click and screenshot without using sleep
    move.click()
    if i == 0:
        time.sleep(0.2)
        # i += 1
        # continue
    elif i == 1:
        time.sleep(0.2)
    for frame in range(frames_per_move):
        board.screenshot(f"./frames/{framenumber:04d}.png")
        framenumber += 1
    i += 1
driver.quit()
