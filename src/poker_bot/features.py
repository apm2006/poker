"""Observable features copied before a recorded betting decision.

Hole cards, winnings, finishing stacks, and subsequent actions are never read.
Player-history statistics and richer board texture remain to be implemented.
"""

STREETS = ('preflop', 'flop', 'turn', 'river')


def decision_snapshot(state, history, previous_actions):
    actor = state.actor_index
    if actor is None:
        return None
    pot = state.total_pot_amount
    to_call = state.checking_or_calling_amount
    effective_stack = min(state.stacks)
    # Heads-up PHH reverses blind posting: p2 is the button/small blind.
    return {
        'actor_index': actor,
        'street': STREETS[state.street_index],
        'position': 'button_small_blind' if actor == 1 else 'big_blind',
        'pot': float(pot),
        'amount_to_call': float(to_call),
        'amount_to_call_over_pot': float(to_call / pot) if pot else None,
        'actor_stack': float(state.stacks[actor]),
        'opponent_stack': float(state.stacks[1 - actor]),
        'effective_stack': float(effective_stack),
        'effective_stack_over_pot': float(effective_stack / pot) if pot else None,
        'board': [card.rank.value + card.suit.value for card in state.get_board_cards(0)],
        'prior_betting_actions': list(previous_actions),
        'raise_legal': state.can_complete_bet_or_raise_to(),
    }
