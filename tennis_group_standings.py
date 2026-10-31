class Player:
    def __init__(self, name):
        self.name = name
        self.wins = 0
        self.losses = 0
        self.sets_won = 0
        self.sets_lost = 0

    def __repr__(self):
        return self.name

def create_matchup(players_group):
    """
    This function creates all the matchups between the group
    :param players_group: The list of players playing for this group
    :type players_group: list
    :return: list of all the matchups
    :rtype: list
    """
    if len(players_group) == 4:
        players_index = [0, 1, 2, 3]
        round_number = [1, 2, 3]
        all_rounds_matchups = []
        for round in round_number:
            first_pair = (players_index[0], players_index[round])
            rest = [p for p in players_index if p not in first_pair]
            second_pair = (rest[0], rest[1])
            current_round_matchup = (first_pair, second_pair)
            all_rounds_matchups.append((current_round_matchup, None))
        return all_rounds_matchups
    
    elif len(players_group) == 3:
        return [
            ([(0, 1)], 2),
            ([(1, 2)], 0),
            ([(0, 2)], 1),
        ]
    
    elif len(players_group) == 5:
        all_rounds_matchups = []
        for i in range(5):
            match1 = ((i + 1) % 5, (i + 4) % 5)
            match2 = ((i + 2) % 5, (i + 3) % 5)
            all_rounds_matchups.append(([match1, match2], i))  # i הוא השחקן הנח
        return all_rounds_matchups

    else:
        print("Error: Group must have 3, 4, or 5 players.")
        return []    


def play_rounds(players_group, all_rounds_matchups):
    """
    Go through all rounds and update wins/losses (and all the data about the scores of the games) based on user input
    :param players_group: List of players (each player is a list with [name, wins, losses, sets lost])
    :param all_rounds_matchups: List of rounds, each round is a tuple of two pairs of indices
    :param types: lists
    """
    head_to_head = {}
    round_counter = 1
    for round_matchup, resting_idx in all_rounds_matchups:
            print(f"\n--- Round {round_counter} ---")
            for pair in round_matchup:
                player1 = players_group[pair[0]]
                player2 = players_group[pair[1]]

                print(f"\nEnter result for {player1.name} vs {player2.name}")
                sets_player1 = int(input(f"Sets won by {player1.name}: "))
                sets_player2 = int(input(f"Sets won by {player2.name}: "))

                head_to_head[(player1.name, player2.name)] = (sets_player1, sets_player2)

                if sets_player1 == 3:
                    player1.wins += 1
                    player2.losses += 1
                elif sets_player2 == 3:
                    player1.losses += 1
                    player2.wins += 1

                player1.sets_won += sets_player1
                player2.sets_won += sets_player2
                player1.sets_lost += sets_player2
                player2.sets_lost += sets_player1

            round_counter += 1
    return head_to_head
 

def get_h2h_winner_and_loser(p1, p2, head_to_head):
    if (p1.name, p2.name) in head_to_head:
        score1, score2 = head_to_head[(p1.name, p2.name)]
        return (p1, p2) if score1 > score2 else (p2, p1)
    else:
        score2, score1 = head_to_head[(p2.name, p1.name)]
        return (p1, p2) if score1 > score2 else (p2, p1)


def rank_players(players_group, head_to_head):
    """
    This function is sorting group of players by their wins, and tie breaks when needed.
    :param players_group: The list of players playing for this group
    :type players_group: list
    :return: The list of the groups, sorted!
    :rtype: list
    """
    tied_win_groups_dic = {}
    for player in players_group:
        current_list = tied_win_groups_dic.get(player.wins, [])
        current_list.append(player)
        tied_win_groups_dic[player.wins] = current_list

    ranked_players = []

    for wins in sorted(tied_win_groups_dic.keys(), reverse=True):
        tied_group = tied_win_groups_dic[wins]

        if len(tied_group) == 0:
            continue

        if len(tied_group) == 1:
            ranked_players.append(tied_group[0])

        elif len(tied_group) == 2:
            winner, loser = get_h2h_winner_and_loser(tied_group[0], tied_group[1], head_to_head)
            ranked_players.extend([winner, loser])

        elif len(tied_group) >= 3:
            tied_group.sort(key=lambda p: (p.sets_won - p.sets_lost, p.sets_won), reverse=True)

            for i in range(len(tied_group)-1):
                p1 = tied_group[i]
                p2 = tied_group[i+1]
                diff1 = p1.sets_won - p1.sets_lost
                diff2 = p2.sets_won - p2.sets_lost             
                
                if diff1 == diff2:
                    winner, loser = get_h2h_winner_and_loser(p1, p2, head_to_head)
                    tied_group[i] = winner
                    tied_group[i+1] = loser

            ranked_players.extend(tied_group)
    
    return ranked_players


def print_ranking(players_group, group_name):
    """
    Print each player's info in a separate line and add a header on top
    :param players_names: List of sorted player names
    :type players_names: list[str]
    :param group_name: The name of the group to display
    :type group_name: str
    """
    #הדפסת כותרת הבית
    print(f"\n{'='*10} {group_name} Ranking {'='*10}\n")

    #הדפסה של הכותרת
    column_width = 12
    header_data = ["Name", "Wins", "Losess", "Sets Won", "Sets Lost"]
    header = "".join(f"{attr:<{column_width}}" for attr in header_data)
    print(header)
    print("-" * len(header))

    #הדפסה של השחקנים
    for player in players_group:
        row_data = [player.name, player.wins, player.losses, player.sets_won, player.sets_lost]
        row = "".join(f"{str(attr):<{column_width}}" for attr in row_data)
        print(row)


def run_group_tournament(players_group, group_name):
    """
    Run the tournament for a single group: create matchups, get results, rank and print.
    :param players_group: list of players
    :param group_name: str, name of the group
    """
    all_rounds = create_matchup(players_group) #יצירת סבבים
    head_to_head = play_rounds(players_group, all_rounds) #הזנת תוצאות ועדכון הטבלה
    ranked_players = rank_players(players_group, head_to_head)
    print_ranking(ranked_players, group_name) #הדפסה של הטבלאות
    return ranked_players


def play_knockout_match(player1, player2, match_name):
    """
    מנהלת משחק יחיד של נוקאאוט ומחזירה טאפל שבו השחקן המנצח הוא הראשון.
    """
    print(f"\n{'='*10} {match_name} {'='*10}")
    print(f"{player1.name} VS {player2.name}")
    
    # קליטה פשוטה וישירה של תוצאות (בלי try)
    sets_1 = int(input(f"Sets won by {player1.name}: "))
    sets_2 = int(input(f"Sets won by {player2.name}: "))
    
    if sets_1 > sets_2:
        print(f"\n>>> {player1.name} wins the {match_name}! <<<")
        return (player1, player2)
    else:
        print(f"\n>>> {player2.name} wins the {match_name}! <<<")
        return (player2, player1)


def run_playoffs(ranked_group_1, ranked_group_2):
    """
    מנהלת את חצאי הגמר והגמר לפי המיקומים משלב הבתים
    """
    print("\n\n" + "#"*35)
    print("🏆 WELCOME TO THE PLAYOFFS 🏆")
    print("#"*35)
    
    # חצי גמר 1: מקום 1 מבית 1 נגד מקום 2 מבית 2 (אינדקס 0 זה מקום ראשון, אינדקס 1 זה מקום שני)
    sf1_winner, sf1_loser = play_knockout_match(ranked_group_1[0], ranked_group_2[1], "Semi-Final 1")
    
    # חצי גמר 2: מקום 1 מבית 2 נגד מקום 2 מבית 1
    sf2_winner, sf2_loser = play_knockout_match(ranked_group_2[0], ranked_group_1[1], "Semi-Final 2")

    # משחק על המקום השלישי
    third_place, fourth_place = play_knockout_match(sf1_loser, sf2_loser, "Third Place Match")
    
    # הגמר הגדול!
    champion, runner_up = play_knockout_match(sf1_winner, sf2_winner, "GRAND FINAL")
    
    print("\n\n" + "=" * 40)
    print("🏅 FINAL TOURNAMENT PODIUM 🏅".center(40))
    print("=" * 40)
    print(f"  🥇 1st Place (Champion):  {champion.name}")
    print(f"  🥈 2nd Place (Runner-Up): {runner_up.name}")
    print(f"  🥉 3rd Place:             {third_place.name}")
    print("=" * 40 + "\n")

    return champion, runner_up, third_place


def setup_group(group_name):
    print(f"\n--- Setup {group_name} ---")
    num_players = int(input(f"How many players in {group_name}? (3, 4, or 5): "))
    group_players = []
    for i in range(num_players):
        name = input(f"Enter name for player {i+1}: ")
        new_player = Player(name)
        group_players.append(new_player)
    return group_players


#main
print("Welcome to the Ultimate Tournament Manager!")
players_group_1 = setup_group("Group 1")
players_group_2 = setup_group("Group 2")
players_list = [players_group_1 + players_group_2]
final_group_1 = run_group_tournament(players_group_1, "Group 1")
final_group_2 = run_group_tournament(players_group_2, "Group 2")
run_playoffs(final_group_1, final_group_2)

