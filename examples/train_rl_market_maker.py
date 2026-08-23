"""Phase 5: trains the Q-learning market maker against the same noise-trader +
informed-trader order flow every other agent has faced, then saves the learned
Q-table as a real artifact (models/q_learning_market_maker.json).

Run with:
    uv run python examples/train_rl_market_maker.py
"""

from pathlib import Path

import matplotlib.pyplot as plt

from mm_sim.agents.rl_market_maker import QLearningMarketMaker
from mm_sim.event_loop import EventLoop
from run_simulation import END_TIME, REFERENCE_PRICE, build_agents

N_EPISODES = 600
EPSILON_START = 0.3
EPSILON_END = 0.02
EPSILON_DECAY = 0.99  # multiplicative, per episode

MODEL_PATH = Path(__file__).parent.parent / "models" / "q_learning_market_maker.json"
OUTPUT_DIR = Path(__file__).parent / "output"


def build_training_agents(rl_agent: QLearningMarketMaker, seed_offset: int) -> list:
    """Same noise-trader + informed-trader flow as run_simulation.py's default
    setup, with the naive market maker swapped out for the RL agent being
    trained.
    """
    agents, _informed_trader, naive_mm = build_agents(seed_offset=seed_offset)
    agents = [a for a in agents if a is not naive_mm]
    agents.append(rl_agent)
    return agents


def main() -> None:
    rl_agent = QLearningMarketMaker(
        agent_id=400,
        reference_price=REFERENCE_PRICE,
        horizon=END_TIME,
        quote_size=10,
        max_inventory=50,
        requote_interval=0.5,
        learning_rate=0.15,
        discount_factor=0.9,
        epsilon=EPSILON_START,
        seed=999,
    )

    episode_final_mtm: list[float] = []

    for episode in range(N_EPISODES):
        rl_agent.reset_episode()
        agents = build_training_agents(rl_agent, seed_offset=episode * 37)
        loop = EventLoop(agents)
        loop.run_until(END_TIME)

        mark_price = loop.book.mid_price if loop.book.mid_price is not None else rl_agent.reference_price
        final_mtm = rl_agent.mark_to_market(mark_price)
        episode_final_mtm.append(final_mtm / 100)  # dollars

        rl_agent.epsilon = max(EPSILON_END, rl_agent.epsilon * EPSILON_DECAY)

        if (episode + 1) % 50 == 0:
            recent = episode_final_mtm[-50:]
            print(
                f"episode {episode + 1:>4}/{N_EPISODES}  "
                f"avg P&L (last 50) = ${sum(recent) / len(recent):8.2f}  "
                f"epsilon={rl_agent.epsilon:.3f}  "
                f"states visited={len(rl_agent.q_table)}"
            )

    MODEL_PATH.parent.mkdir(exist_ok=True)
    rl_agent.save(MODEL_PATH)
    print(f"\nSaved trained model to {MODEL_PATH} ({len(rl_agent.q_table)} states visited)")

    OUTPUT_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(episode_final_mtm, linewidth=0.6, alpha=0.5, label="per-episode")
    window = 30
    if len(episode_final_mtm) >= window:
        rolling = [
            sum(episode_final_mtm[max(0, i - window) : i + 1]) / len(episode_final_mtm[max(0, i - window) : i + 1])
            for i in range(len(episode_final_mtm))
        ]
        ax.plot(rolling, linewidth=1.5, label=f"{window}-episode rolling avg")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("episode")
    ax.set_ylabel("final mark-to-market P&L ($)")
    ax.set_title("Q-learning market maker: training curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "phase5_training_curve.png", dpi=150)
    print(f"Saved training curve to {OUTPUT_DIR / 'phase5_training_curve.png'}")


if __name__ == "__main__":
    main()
