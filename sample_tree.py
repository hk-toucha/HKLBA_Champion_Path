import math
from typing import List, Union

def generate_tournament(teams: List[str]) -> List[Union[str, List]]:
    """
    Generate a single-elimination tournament tree for a list of teams.
    Teams should be a power of 2 (e.g., 8, 16).
    Returns a nested list representing the tournament tree.
    """
    num_teams = len(teams)
    if num_teams < 2 or math.log2(num_teams).is_integer() is False:
        raise ValueError("Number of teams must be a power of 2")

    def build_round(team_list: List[str]) -> List[Union[str, List]]:
        if len(team_list) == 1:
            return team_list
        matches = []
        for i in range(0, len(team_list), 2):
            # Pair teams (e.g., 1 vs 16, 8 vs 9)
            match = [team_list[i], team_list[i + 1]]
            matches.append(match)
        # Recursively build next round
        return matches if len(matches) > 1 else build_round([f"Winner of {matches[0][0]} vs {matches[0][1]}"])

    # Seed teams to avoid top seeds meeting early (e.g., 1 vs 16, 2 vs 15)
    sorted_teams = []
    for i in range(num_teams // 2):
        sorted_teams.append(teams[i])
        sorted_teams.append(teams[num_teams - 1 - i])
    
    return build_round(sorted_teams)

def print_tournament_tree(tournament: List, level: int = 0, prefix: str = "") -> None:
    """
    Print the tournament tree in a readable format.
    """
    for i, node in enumerate(tournament):
        indent = "  " * level
        if isinstance(node, str):
            print(f"{indent}{prefix}{node}")
        else:
            print(f"{indent}{prefix}Match {i + 1}: {node[0]} vs {node[1]}")
            print_tournament_tree([f"Winner of {node[0]} vs {node[1]}"], level + 1, prefix)

# Example usage
if __name__ == "__main__":
    teams = [f"Team {i+1}" for i in range(8)]  # Example: 8 teams
    tournament = generate_tournament(teams)
    print("Tournament Fixture Tree:")
    print_tournament_tree(tournament)