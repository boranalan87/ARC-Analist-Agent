    ) -> GameAction:

        state = latest_frame.state

        if state in (
            GameState.NOT_PLAYED,
            GameState.GAME_OVER,
        ):
            if state is GameState.GAME_OVER:
                self.policy.observe(
                    observation_key(
                        latest_frame.frame,
                        latest_frame.levels_completed,
                        state.name,
                    ),
                    latest_frame.levels_completed,
                    state.name,
                )

            self.policy.clear_pending()

            action = GameAction.RESET
            action.reasoning = "Start or restart game"
            return action

        key = observation_key(
            latest_frame.frame,
            latest_frame.levels_completed,
            state.name,
        )

        self.policy.observe(
            key,
            latest_frame.levels_completed,
            state.name,
        )

        action_name = self.policy.choose(
            key,
            latest_frame.levels_completed,
        )

        action = GameAction.from_name(action_name)

        action.reasoning = (
            f"FeedbackExplorer: {action_name}; "
            f"state_visits={self.policy.visits[key]}; "
            f"trials={self.policy.attempts[(key, action_name)]}"
        )

        return action

    def take_action(
        self,
        action: GameAction,
    ) -> FrameData | None:
        """Execute action and collect its observed outcome."""

        before = self.frames[-1]

        after = super().take_action(action)

        if after is not None:
            self.diagnostics.record_action(
                action=action.name,
                before_frame=before.frame,
                after_frame=after.frame,
                before_levels=before.levels_completed,
                after_levels=after.levels_completed,
                after_state=after.state.name,
            )

        return after
