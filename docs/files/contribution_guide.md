# BERA Tools Contribution Flowchart

```mermaid
flowchart TD
    A([Want to contribute to a BERA Tools project?])
    B{What is your experience level?}
    A --> B
    B --> C1[User]
    B --> C2[Casual Developer]
    B --> C3[Experienced Developer]
    C1 --> D1[Found a bug or have a suggestion?]
    D1 --> E1[Report an Issue]
    E1 --> F1[Wait for feedback or updates]
    F1 --> G1([Contribution complete])
    C2 --> D2[Want to fix a bug or add a small feature?]
    D2 --> E2[Fork the repository]
    E2 --> F2[Make changes in your fork]
    F2 --> G2[Submit a Pull Request]
    G2 --> H2[Discuss in PR or Issue comments]
    H2 --> I2([Contribution submitted])
    C3 --> D3[Check for existing Issues/PRs]
    D3 --> E3[Create a branch or fork]
    E3 --> F3[Make substantial changes, follow guidelines]
    F3 --> G3[Submit a Pull Request, reference Issues]
    G3 --> H3[Review code and help others]
    H3 --> I3([Contribution submitted])