import os
import asyncio
import logging

# Set logging level to suppress warnings
logging.getLogger().setLevel(logging.ERROR)
# Just disables the warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# This import is only to help PyInstaller when generating the executables
import tensorflow as tf

import deck52
import pprint
import time
import json
import asyncio
import uuid
import shelve
import os 
import argparse
import numpy as np

import human
import bots
import conf

from sample import Sample
from bidding import bidding
from sample import Sample
from deck52 import decode_card
from bidding.binary import DealData
from objects import CardResp, Card, BidResp
from claim import Claimer
from pbn2ben import load
from util import calculate_seed

def get_execution_path():
    # Get the directory where the program is started from either PyInstaller executable or the script
    return os.getcwd()


def random_deal(number=None):
    deal_str = deck52.random_deal()
    if number == None:
        number = np.random.randint(1, 17)
    auction_str = deck52.board_dealer_vuln(number)

    return deal_str, auction_str


class AsyncBotBid(bots.BotBid):
    async def async_bid(self, auction):
        return self.bid(auction)

class AsyncBotLead(bots.BotLead):
    async def async_lead(self, auction):
        return self.find_opening_lead(auction)

class AsyncCardPlayer(bots.CardPlayer):
    async def async_play_card(self, trick_i, leader_i, current_trick52, players_states, bidding_scores):
        return self.play_card(trick_i, leader_i, current_trick52, players_states, bidding_scores)
    
    
class Driver:

    def __init__(self, models, factory, sampler, verbose):
        self.models = models
        self.sampler = sampler
        self.factory = factory
        self.confirmer = factory.create_confirmer()
        self.channel = factory.create_channel()

        print("Setting seed=42")
        np.random.seed(42)

        #Default is a Human South
        self.human = [False, False, True, False]
        self.human_declare = False
        self.rotate = False
        self.name = "Human"
        self.ns = models.ns
        self.ew = models.ew
        self.verbose = verbose
        self.play_only = False
        self.claim = models.claim

    def set_deal(self, board_number, deal_str, auction_str, play_only = None, bidding_only=False):
        self.board_number = board_number
        self.deal_str = deal_str
        self.hands = deal_str.split()
        self.deal_data = DealData.from_deal_auction_string(self.deal_str, auction_str, self.ns, self.ew, 32)

        auction_part = auction_str.split(' ')
        if play_only == None and len(auction_part) > 2: play_only = True
        if play_only:
            self.auction = self.deal_data.auction
            self.play_only = play_only
        self.bidding_only = bidding_only
        if self.rotate:
            self.dealer_i = (self.deal_data.dealer + 1) % 4
            self.vuln_ns = self.deal_data.vuln_ew
            self.vuln_ew = self.deal_data.vuln_ns
            self.hands.insert(0, self.hands.pop())
            self.deal_str = " ".join(self.hands)
            print("Rotated deal: "+self.deal_str)
        else:
            self.dealer_i = self.deal_data.dealer
            self.vuln_ns = self.deal_data.vuln_ns
            self.vuln_ew = self.deal_data.vuln_ew
        self.trick_winners = []

        # Now you can use hash_integer as a seed
        hash_integer = calculate_seed(deal_str)
        if self.verbose:
            print("Setting seed (Full deal)=",hash_integer)
        np.random.seed(hash_integer)


    async def run(self):
        result_list = self.hands.copy()

        print(self.human)
        print(result_list)
        # If human involved hide the unseen hands
        if np.any(np.array(self.human)):
            for i in range(len(self.human)):
                if not self.human[i]:
                    result_list[i] = ""

        await self.channel.send(json.dumps({
            'message': 'deal_start',
            'dealer': self.dealer_i,
            'vuln': [self.vuln_ns, self.vuln_ew],
            'hand': result_list,
            'name': self.name
        }))

        self.bid_responses = []
        self.card_responses = []

        if self.play_only:
            auction = self.auction
            for bid in auction:
                if bidding.BID2ID[bid] > 1:
                    self.bid_responses.append(BidResp(bid=bid, candidates=[], samples=[], shape=-1, hcp=-1, who="PlayOnly"))
        else:
            auction = await self.bidding()

        self.contract = bidding.get_contract(auction)

        if self.contract is None:
            await self.channel.send(json.dumps({
                'message': 'deal_end',
                'pbn': self.deal_str,
                'dict': self.to_dict()
            }))
            return

        strain_i = bidding.get_strain_i(self.contract)
        decl_i = bidding.get_decl_i(self.contract)

        await self.channel.send(json.dumps({
            'message': 'auction_end',
            'declarer': decl_i,
            'auction': auction,
            'strain': strain_i
        }))

        if self.bidding_only:
            return
        
        print("trick 1")

        opening_lead52 = (await self.opening_lead(auction)).card.code()

        await self.channel.send(json.dumps({
            'message': 'card_played',
            'player': (decl_i + 1) % 4,
            'card': decode_card(opening_lead52)
        }))

        # If human is dummy display declarers hand
        if self.human[(decl_i + 2) % 4]:
            hand = self.deal_str.split()[decl_i]
            await self.channel.send(json.dumps({
                'message': 'show_dummy',
                'player': decl_i,
                'dummy': hand
            }))
        else:
            # dummys hand
            hand = self.deal_str.split()[(decl_i + 2) % 4]
            await self.channel.send(json.dumps({
                'message': 'show_dummy',
                'player': (decl_i + 2) % 4,
                'dummy': hand
            }))

        if self.verbose: 
            for card_resp in self.card_responses:
                pprint.pprint(card_resp.to_dict(), width=200)
        
        await self.play(auction, opening_lead52)

        await self.channel.send(json.dumps({
            'message': 'deal_end',
            'pbn': self.deal_str,
            'dict': self.to_dict()
        }))

    def to_dict(self):
        return {
            'timestamp': time.time(),
            'dealer': self.dealer_i,
            'vuln_ns': self.vuln_ns,
            'vuln_ew': self.vuln_ew,
            'hands': self.deal_str,
            'bids': [b.to_dict() for b in self.bid_responses],
            'contract': self.contract,
            'play': [c.to_dict() for c in self.card_responses],
            'trick_winners': self.trick_winners,
            'board_number' : self.board_number,
            'human': self.name
        }

    async def play(self, auction, opening_lead52):
        contract = bidding.get_contract(auction)
        
        level = int(contract[0])
        strain_i = bidding.get_strain_i(contract)
        decl_i = bidding.get_decl_i(contract)
        is_decl_vuln = [self.vuln_ns, self.vuln_ew, self.vuln_ns, self.vuln_ew][decl_i]

        lefty_hand = self.hands[(decl_i + 1) % 4]
        dummy_hand = self.hands[(decl_i + 2) % 4]
        righty_hand = self.hands[(decl_i + 3) % 4]
        decl_hand = self.hands[decl_i]

        card_players = [
            AsyncCardPlayer(self.models, 0, lefty_hand, dummy_hand, contract, is_decl_vuln, self.verbose),
            AsyncCardPlayer(self.models, 1, dummy_hand, decl_hand, contract, is_decl_vuln, self.verbose),
            AsyncCardPlayer(self.models, 2, righty_hand, dummy_hand, contract, is_decl_vuln, self.verbose),
            AsyncCardPlayer(self.models, 3, decl_hand, dummy_hand, contract, is_decl_vuln, self.verbose)
        ]

        # check if user is playing and update card players accordingly
        # the card players are allways positioned relative to declarer (lefty = 0, dummy = 1 ...)
        for i in range(4): 
            if self.human[i]:
                # We are declarer or human declare and dummy
                if decl_i == i or self.human_declare and decl_i == (i + 2) % 4:
                    card_players[3] = self.factory.create_human_cardplayer(self.models, 3, decl_hand, dummy_hand, contract, is_decl_vuln)
                    card_players[1] = self.factory.create_human_cardplayer(self.models, 1, dummy_hand, decl_hand, contract, is_decl_vuln)
                    
                # We are lefty
                if i == (decl_i + 1) % 4:
                    card_players[0] = self.factory.create_human_cardplayer(self.models, 0, lefty_hand, dummy_hand, contract, is_decl_vuln)
                # We are righty
                if i == (decl_i + 3) % 4:
                    card_players[2] = self.factory.create_human_cardplayer(self.models, 2, righty_hand, dummy_hand, contract, is_decl_vuln)

        claimer = Claimer(self.verbose)

        player_cards_played = [[] for _ in range(4)]
        shown_out_suits = [set() for _ in range(4)]

        leader_i = 0

        tricks = []
        tricks52 = []
        trick_won_by = []

        opening_lead = deck52.card52to32(opening_lead52)

        current_trick = [opening_lead]
        current_trick52 = [opening_lead52]

        card_players[0].hand52[opening_lead52] -= 1

        for trick_i in range(12):
            if trick_i != 0:
                print("trick {}".format(trick_i+1))

            for player_i in map(lambda x: x % 4, range(leader_i, leader_i + 4)):
                if self.verbose:
                    print('player {}'.format(player_i))
                
                if trick_i == 0 and player_i == 0:
                    # To get the state right we ask for the play when using Tf.2X
                    if self.verbose:
                        print('skipping opening lead for ',player_i)
                    for i, card_player in enumerate(card_players):
                        card_player.set_card_played(trick_i=trick_i, leader_i=leader_i, i=0, card=opening_lead)
                    continue

                # Don't calculate claim before trick 6    
                if self.claim and trick_i > 5 and len(current_trick) == 0 and player_i in (1, 3):
                    claimer.claim(
                        strain_i=strain_i,
                        player_i=player_i,
                        hands52=[card_player.hand52 for card_player in card_players],
                        n_samples=20
                    )

                if isinstance(card_players[player_i], bots.CardPlayer):
                    rollout_states, bidding_scores, c_hcp, c_shp = self.sampler.init_rollout_states(trick_i, player_i, card_players, player_cards_played, shown_out_suits, current_trick, auction, card_players[player_i].hand.reshape(
                        (-1, 32)), [self.vuln_ns, self.vuln_ew], self.models)
                    assert rollout_states[0].shape[0] > 0, "No samples for DDSolver"

                else: 
                    rollout_states = None
                    bidding_scores = None
                    c_hcp = -1
                    c_shp = -1

                await asyncio.sleep(0.01)

                card_resp = await card_players[player_i].async_play_card(trick_i, leader_i, current_trick52, rollout_states, bidding_scores)
                
                card_resp.hcp = c_hcp
                card_resp.shape = c_shp
                if self.verbose:
                    pprint.pprint(card_resp.to_dict(), width=200)
                
                await asyncio.sleep(0.01)

                self.card_responses.append(card_resp)

                card52 = card_resp.card.code()

                await self.channel.send(json.dumps({
                    'message': 'card_played',
                    'player': ((decl_i + 1) % 4 + player_i) % 4,
                    'card': card_resp.card.symbol()
                }))

                card = deck52.card52to32(card52)

                for card_player in card_players:
                    card_player.set_card_played(trick_i=trick_i, leader_i=leader_i, i=player_i, card=card)

                current_trick.append(card)

                current_trick52.append(card52)

                card_players[player_i].set_own_card_played52(card52)
                if player_i == 1:
                    for i in [0, 2, 3]:
                        card_players[i].set_public_card_played52(card52)
                if player_i == 3:
                    card_players[1].set_public_card_played52(card52)

                # update shown out state
                if card // 8 != current_trick[0] // 8:  # card is different suit than lead card
                    shown_out_suits[player_i].add(current_trick[0] // 8)

            # sanity checks after trick completed
            assert len(current_trick) == 4

            for i, card_player in enumerate(card_players):
                assert np.min(card_player.hand52) == 0
                assert np.min(card_player.public52) == 0
                assert np.sum(card_player.hand52) == 13 - trick_i - 1
                assert np.sum(card_player.public52) == 13 - trick_i - 1

            tricks.append(current_trick)
            tricks52.append(current_trick52)

            # initializing for the next trick
            # initialize hands
            for i, card in enumerate(current_trick):
                card_players[(leader_i + i) % 4].x_play[:, trick_i + 1, 0:32] = card_players[(leader_i + i) % 4].x_play[:, trick_i, 0:32]
                card_players[(leader_i + i) % 4].x_play[:, trick_i + 1, 0 + card] -= 1

            # initialize public hands
            for i in (0, 2, 3):
                card_players[i].x_play[:, trick_i + 1, 32:64] = card_players[1].x_play[:, trick_i + 1, 0:32]
            card_players[1].x_play[:, trick_i + 1, 32:64] = card_players[3].x_play[:, trick_i + 1, 0:32]

            for card_player in card_players:
                # initialize last trick
                for i, card in enumerate(current_trick):
                    card_player.x_play[:, trick_i + 1, 64 + i * 32 + card] = 1
                    
                # initialize last trick leader
                card_player.x_play[:, trick_i + 1, 288 + leader_i] = 1

                # initialize level
                card_player.x_play[:, trick_i + 1, 292] = level

                # initialize strain
                card_player.x_play[:, trick_i + 1, 293 + strain_i] = 1

            # sanity checks for next trick
            for i, card_player in enumerate(card_players):
                assert np.min(card_player.x_play[:, trick_i + 1, 0:32]) == 0
                assert np.min(card_player.x_play[:, trick_i + 1, 32:64]) == 0
                assert np.sum(card_player.x_play[:, trick_i + 1, 0:32], axis=1) == 13 - trick_i - 1
                assert np.sum(card_player.x_play[:, trick_i + 1, 32:64], axis=1) == 13 - trick_i - 1

            trick_winner = (leader_i + deck52.get_trick_winner_i(current_trick52, (strain_i - 1) % 5)) % 4
            trick_won_by.append(trick_winner)

            if trick_winner % 2 == 0:
                card_players[0].n_tricks_taken += 1
                card_players[2].n_tricks_taken += 1
            else:
                card_players[1].n_tricks_taken += 1
                card_players[3].n_tricks_taken += 1

            if self.verbose:
                print('trick52 {} cards={}. won by {}'.format(trick_i+1, list(map(decode_card, current_trick52)), trick_winner))
            if np.any(np.array(self.human)):
                key = await self.confirmer.confirm()
                if key == 'q':
                    print(self.deal_str)
                    return
            else:
                await self.confirmer.confirm()

            # update cards shown
            for i, card in enumerate(current_trick):
                player_cards_played[(leader_i + i) % 4].append(card)
            
            leader_i = trick_winner
            current_trick = []
            current_trick52 = []

        # play last trick
        print("trick 13")
        for player_i in map(lambda x: x % 4, range(leader_i, leader_i + 4)):
            
            if not isinstance(card_players[player_i], bots.CardPlayer):
                await card_players[player_i].get_card_input()

            card52 = np.nonzero(card_players[player_i].hand52)[0][0]
            card =deck52.card52to32(card52)

            card_resp = CardResp(card=Card.from_code(card52), candidates=[], samples=[], shape=-1, hcp=-1)

            await self.channel.send(json.dumps({
                'message': 'card_played',
                'player': ((decl_i + 1) % 4 + player_i) % 4,
                'card': card_resp.card.symbol()
            }))

            self.card_responses.append(card_resp)
            
            current_trick.append(card)
            current_trick52.append(card52)

        await self.confirmer.confirm()

        tricks.append(current_trick)
        tricks52.append(current_trick52)
        
        trick_winner = (leader_i + deck52.get_trick_winner_i(current_trick52, (strain_i - 1) % 5)) % 4
        if trick_winner % 2 == 0:
            card_players[0].n_tricks_taken += 1
            card_players[2].n_tricks_taken += 1
        else:
            card_players[1].n_tricks_taken += 1
            card_players[3].n_tricks_taken += 1


        trick_won_by.append(trick_winner)
        if self.verbose:
            print('trick52 {} cards={}. won by {}'.format(trick_i+1, list(map(decode_card, current_trick52)), trick_winner))

        # Decode each element of tricks52
        decoded_tricks52 = [[deck52.decode_card(item) for item in inner] for inner in tricks52]
        pprint.pprint(list(zip(decoded_tricks52, trick_won_by)))

        self.trick_winners = trick_won_by

        # Print contract and result
        print("Contract: ",self.contract, card_players[3].n_tricks_taken, "tricks")

    
    async def opening_lead(self, auction):

        hash_integer = calculate_seed(self.deal_str)
        # Now you can use hash_integer as a seed
        if self.verbose:
            print("Setting seed (Opening lead)=",hash_integer)
        np.random.seed(hash_integer)

        contract = bidding.get_contract(auction)
        decl_i = bidding.get_decl_i(contract)

        hands_str = self.deal_str.split()

        await asyncio.sleep(0.01)

        if self.human[(decl_i + 1) % 4]:
            card_resp = await self.factory.create_human_leader().async_lead()
        else:
            bot_lead = AsyncBotLead(
                [self.vuln_ns, self.vuln_ew], 
                hands_str[(decl_i + 1) % 4], 
                self.models,
                self.sampler,
                self.verbose
            )
            card_resp = await bot_lead.async_lead(auction)

        await asyncio.sleep(0.01)

        self.card_responses.append(card_resp)

        return card_resp

    async def bidding(self):
        hands_str = self.deal_str.split()
        
        vuln = [self.vuln_ns, self.vuln_ew]

        players = []
        for i, level in enumerate(self.human):
            if self.models.use_bba:
                from bba.BBA import BBABotBid
                players.append(BBABotBid(self.models.ns, self.models.ew, i, hands_str[i], vuln, self.dealer_i))
            elif level == 1:
                players.append(self.factory.create_human_bidder(vuln, hands_str[i], self.name))
            else:
                bot = AsyncBotBid(vuln, hands_str[i], self.models, self.sampler, i, self.verbose)
                players.append(bot)

        auction = ['PAD_START'] * self.dealer_i

        player_i = self.dealer_i

        while not bidding.auction_over(auction):
            bid_resp = await players[player_i].async_bid(auction)
            if bid_resp.bid == "Hint":
                await self.channel.send(json.dumps({
                    'message': 'hint',
                    'bids': "Asking BEN"
                }))

                await asyncio.sleep(0.1)
            else :
                self.bid_responses.append(bid_resp)

                auction.append(bid_resp.bid)

                await self.channel.send(json.dumps({
                    'message': 'bid_made',
                    'auction': auction
                }))

                player_i = (player_i + 1) % 4
                # give time to client to redraw
                await asyncio.sleep(0.1)
            
        return auction

def random_deal_source():
    while True:
        yield random_deal()

async def main():
    random = True
    #For some strange reason parameters parsed to the handler must be an array
    board_no = []
    board_no.append(0) 

    # Get the path to the config file
    config_path = get_execution_path()
    
    base_path = os.getenv('BEN_HOME') or config_path

    parser = argparse.ArgumentParser(description="Game server")
    parser.add_argument("--boards", default="", help="Filename for configuration")
    parser.add_argument("--auto", type=bool, default=False, help="Continue without user confirmation. If a file is provided it will stop at end of file")
    parser.add_argument("--boardno", default=0, type=int, help="Board number to start from")
    parser.add_argument("--config", default=f"{base_path}/config/default.conf", help="Filename for configuration")
    parser.add_argument("--playonly", type=bool, default=False, help="Just play, no bidding")
    parser.add_argument("--biddingonly", type=bool, default=False, help="Just bidding, no play")
    parser.add_argument("--verbose", type=bool, default=False, help="Output samples and other information during play")

    args = parser.parse_args()

    configfile = args.config
    verbose = args.verbose
    auto = args.auto
    play_only = args.playonly
    bidding_only = args.biddingonly
    boards = []

    if args.boards:
        filename = args.boards
        file_extension = os.path.splitext(filename)[1].lower()  
        if file_extension == '.ben':
            with open(filename, "r") as file:
                board_no.append(0) 
                lines = file.readlines()  # 
                # Loop through the lines, grouping them into objects
                for i in range(0, len(lines), 2):
                    board = {
                        'deal': lines[i].strip(),      
                        'auction': lines[i+1].strip().replace('NT','N')  
                    }
                    boards.append(board)            
            print(f"{len(boards)} boards loaded from file")
            random = False
        if file_extension == '.pbn':
            with open(filename, "r") as file:
                lines = file.readlines()
                boards = load(lines)
                print(f"{len(boards)} boards loaded from file")
            random = False

    if args.boardno:
        print(f"Starting from {args.boardno}")
        board_no[0] = args.boardno - 1

    if random:
        print("Playing random deals or deals from the client")
 
    np.set_printoptions(precision=1, suppress=True, linewidth=200)

    configuration = conf.load(configfile)
        
    try:
        if (configuration["models"]['tf_version'] == "2"):
            print("Loading version 2")
            from nn.models_tf2 import Models
        else: 
            # Default to version 1. of Tensorflow
            from nn.models import Models
    except KeyError:
            # Default to version 1. of Tensorflow
            from nn.models import Models

    models = Models.from_conf(configuration, base_path.replace(os.path.sep + "src",""))

    driver = Driver(models, human.ConsoleFactory(), Sample.from_conf(configuration, verbose), verbose)

    while True:
        if random: 
            #Just take a random"
            rdeal = random_deal()

            # example of to use a fixed deal
            # rdeal = ('AK.AKQ6.AK85.AKQ Q6532.97.743.653 JT7.JT5.QJT96.T4 984.8432.2.J9872', 'E E-W')

            print(f"Playing Board: {rdeal}")
            driver.set_deal(None, *rdeal, False, bidding_only=bidding_only)
        else:
            rdeal = boards[board_no[0]]['deal']
            auction = boards[board_no[0]]['auction']
            print(f"Board: {board_no[0]+1} {rdeal}")
            driver.set_deal(board_no[0] + 1, rdeal, auction, play_only=play_only, bidding_only=bidding_only)
            board_no[0] = (board_no[0] + 1)

        # BEN is handling all 4 hands
        driver.human = [False, False, False, False]
        t_start = time.time()
        await driver.run()

        if not bidding_only:
            with shelve.open(f"{base_path}/gamedb") as db:
                deal = driver.to_dict()
                print("Saving Board: ",driver.hands)
                print(f'Board played in {time.time() - t_start:0.1f} seconds')
                db[uuid.uuid4().hex] = deal

        if not auto:
            user_input = input("\n Q to quit or any other key for next deal ")
            if user_input.lower() == "q":
                break
        else:
            if args.boards and board_no[0] >= len(boards):
                break

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
