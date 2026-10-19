Goal is to build a online judge system integrated with state of the art converstational AI to achieve the goal of transitioning the act of coding puzzles passively into a active act. 

The core functional requirements of the application are:
1. The user should be able to view the list of coding problems and retrieve individual problem descriptions and code stubs
2. Submit source code in multiple languages and receive graded verdict
3. Session lifecycle -> the system must allow the user to initiate, resume, conclude or abandon an interation problem solving section tied to a specific problem
4. Deterministic state transitions: The system must enforce a structured, phased interview progression: 1. Clarification 2. Time complexity analysis and initial question discussion 3. Coding 4. Dry Run and Testing 5. Follow-up/Variants 6. Debrief and scorecard
5. System must maintain ephemeral state synchronization
6. The application supports a converstation AI interaction agent which supports socratic interaction, context-aware responses, multi-tier hint escalation ladder, Real-time code observation, dynamic variant generation, post-interview rubric
7. The editor must debounce and stream code snapshots to the backend over websockets without manual save triggers, boilerplat and signature seeding.
8. Real-time communication
9. Isolated sandboxed execution, test suite evaluation, custom input evaluation, execution telemetry, context injection
