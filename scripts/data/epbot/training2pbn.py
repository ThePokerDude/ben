import datetime
import sys

from collections import deque
from typing import NamedTuple


class Deal(NamedTuple):
    dealer: str
    vulnerable: str
    hands: str

def pbn_generator(boards):

    def print_deal(board_number, dlr, vul, deal, dealer, auction):
        print('[Event "BEN"]')
        print('[Site "BEN"]')
        print(f'[Date "{datetime.datetime.now().date().isoformat()}"]')
        print(f'[Board "{board_number}"]')
        print('[West "BEN"]')
        print('[North "BEN"]')
        print('[East "BEN"]')
        print('[South "BEN"]')
        print('[Scoring "IMP"]')
        print(f'[Dealer "{dlr}"]')
        print(f'[Vulnerable "{vul}"]')
        print(f'[Deal "{deal}"]')
        if len(auction) > 0: 
            print(f'[Auction "{dealer}"]')
            # Define the number of elements per line
            elements_per_line = 4

            # Iterate through the array
            for i, element in enumerate(auction):
            # Print the element
                print(element, end=" ")

                # Check if it's time to insert a line feed
                if (i + 1) % elements_per_line == 0:
                    print()  # Insert a line feed

            # Ensure the last line ends with a line feed
            if len(auction) % elements_per_line != 0:
                print()
        print('[Declarer "?"]')
        print('[Result "?"]\n')

    for i in range(len(boards) // 2):
        deal_str = boards[i*2]
        parts = boards[i*2+1].split()
        dealer_str = parts[0]
        vulnerable_str = parts[1].replace("-","")
        print_deal(i + 1, dealer_str, vulnerable_str, f'N:{deal_str}', dealer_str, parts[2:])
        

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python training2pbn.py training.txt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    try:
        with open(input_file, "r", encoding='utf-8') as file:  # Open the input file with UTF-8 encoding
            lines = file.readlines()
            lines = [line.strip() for line in lines]
        pbn_generator(lines)
    except Exception as ex:
        print('Error:', ex)
        raise ex
