# Contributing

Thank you for your interest in improving BERA Tools. Whether you are a user, a new developer, or an experienced contributor, your involvement is highly valued. This guide will help you find the best way to participate.

## BERA Tools Contribution Flowchart

```mermaid
flowchart TD
    A([Interested in contributing to a BERA Tools project?])
    B{Are you a User or a Developer?}
    A --> B
    B --> C1[User]
    B --> C2[Developer]

    C1 --> D1[Check documentation and issue tracker]
    D1 --> E1[Submit an Issue]
    E1 --> F1[Await feedback or updates]

    C2 --> G{Direct access to repository?}
    G --> H1[Yes: Create a branch]
    G --> H2[No: Fork repository]
    H2 --> I2[Create a branch in your fork]
    H1 --> J2[Make changes]
    I2 --> J2
    J2 --> K2[Submit a Pull Request]
    K2 --> L2[Participate in discussion]
    L2 --> M2([Contribution complete!])

    click E1 "https://github.com/appliedgrg/beratools/issues" "Submit an Issue"
```

## For Non-developers

### Reporting Issues :material-bug:

We appreciate your help in making BERA Tools better! If you encounter a issue or have a suggestion, please:

1. **Review the documentation** and **search the issue tracker** to see if your question or issue has already been addressed.

2. When submitting a new issue, include as much detail as possible:
    - BERA Tools version
    - Operating system
    - Python version
    - Any error messages from the console
    - A clear description of the problem
    - Steps or examples to reproduce the issue (screenshots are welcome, but please include text/code for easy copy/paste when possible)

3. Be ready to answer follow-up questions or provide additional information if needed. Your input helps us resolve issues more quickly!

### Helping Others :material-comment-question:

If you see questions or issues from other users, feel free to share your knowledge and suggestions. Your experience can make a big difference in the community.

### Improving Documentation :material-pencil:

We strive to keep our documentation clear and helpful, but there is always room for improvement. If you notice something missing or unclear, please help us by suggesting changes or additions. See the [Development Guide](./development.md) for more information.

## For Developers

### Contribution Process :material-handshake:

If you want to contribute code, follow this process:

1. **Check your repository access:**
    - If you have direct access, create a new branch from the main repository.
    - If you do not have direct access, fork the repository and create a branch in your fork.

2. **Make your changes** on your branch.

3. **Submit a Pull Request** from your branch (or fork) to the main repository.

4. **Participate in discussion** and respond to feedback on your PR.

For more details on environment setup and guidelines, see the [Development Guide](./development.md).

### Reviewing Code :material-glasses:

Participate in code reviews by providing constructive feedback and suggestions. Collaborating on code helps us maintain high quality and encourages learning and growth for everyone involved.

---

Thank you for being part of the BERA Tools community!
