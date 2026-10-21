            elif key == old_key:
                reward = -2.0

            elif first_visit:
                reward = 3.0

            else:
                reward = 0.5

            self.reward_sum[pair] += reward
            self.next_screen[pair] = key

            self._pending = None

            # A new level starts a new movement context.
            if progressed or state in ("WIN", "GAME_OVER"):
                self._last_action = None

        self.visits[key] += 1

    def _candidate_actions(self) -> list[str]:
        """Return actions allowed by the optional V5 rule."""

        candidates = list(self.actions)

        if not self.avoid_immediate_reverse:
            return candidates

        opposite = OPPOSITE_ACTIONS.get(
            self._last_action
        )

        if opposite is None:
            return candidates

        filtered = [
            action
            for action in candidates
            if action != opposite
        ]

        # Always keep at least one valid action available.
        return filtered if filtered else candidates

    def choose(
        self,
        key: str,
        levels_completed: int,
    ) -> str:
        """Select an action using balanced exploration.

        V5 optionally excludes the immediate reverse direction.
        Among untried actions, choose the least-used action.
        Once candidate actions have been explored, use their
        observed rewards, novelty and exploration bonuses.
        """

        candidates = self._candidate_actions()

        unseen = [
            action
            for action in candidates
            if self.attempts[(key, action)] == 0
        ]

        if unseen:

            total_usage = Counter()

            for (_, action), count in self.attempts.items():
                total_usage[action] += count

            action = min(
                unseen,
                key=lambda candidate: (
                    total_usage[candidate],
                    self.actions.index(candidate),
                ),
            )

        else:

            def value(action_name: str) -> float:

                pair = (key, action_name)

                count = self.attempts[pair]

                mean_reward = (
                    self.reward_sum[pair] / count
                )

                destination = self.next_screen.get(pair)

                if destination:
                    novelty = (
                        1.5
                        / sqrt(
                            1 + self.visits[destination]
                        )
                    )
                else:
                    novelty = 0.0

                exploration_bonus = (
                    0.5 / sqrt(count)
                )

                repeat_penalty = (
                    0.1 * count
                )

                return (
                    mean_reward
                    + novelty
                    + exploration_bonus
                    - repeat_penalty
                )

            action = max(
                candidates,
                key=value,
            )

        self.attempts[(key, action)] += 1

        self._pending = (
            key,
