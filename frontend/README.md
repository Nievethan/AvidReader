# AvidReader Frontend (Flutter)

A cross-platform Flutter application providing an immersive, classical literature-themed reading experience with grounded AI reading assistance, on-demand character relationship extraction, vocabulary tracking (Word Wall), and reading habit milestones.

---

## 🏛 Visual Language & Design System

The app is built around the **Classic Literature Theme** (`lib/theme/classic_lit_theme.dart`):
- **Parchment & Rag Paper**: Cream background (`#F6F1E7`), linen cards (`#EFE8D8`), and elevated paper sheets (`#FAF7F0`).
- **Typography & Ink**: Georgia serif headers and iron gall ink typography (`#231F1D`) with sepia secondary text (`#645951`).
- **Accents**: Moroccan leather burgundy / oxblood (`#6E262E`), banker's lamp green (`#2D4A3E`), and antique gilded gold (`#C59B27`).

---

## 📱 App Structure & Screens

The app navigation is organized around a 5-tab dashboard shell (`lib/screens/reading_dashboard_shell.dart`):

1. **Library (`lib/screens/library_screen.dart`)**:
   - Lists uploaded books with spine colors and cover thumbnails.
   - Shows active reading progress and ingestion status (`processing`, `ready`, `failed`).
   - Book upload via native file chooser.
   - Book deletion (`DELETE /api/v1/books/{id}`) with cascade cleanup.

2. **Reader (`lib/screens/reader_screen.dart`)**:
   - Real extracted page/chapter content (`GET /api/v1/books/{id}/content`).
   - Page-by-page progress synchronization (`PUT /api/v1/books/{id}/progress`), auto-logging daily streaks.
   - Typography controls (cycling reading font size).
   - "Explain" action for grounded AI passage explanation (`POST /api/v1/ai/chat` with `interaction_type: explain`).
   - Direct "Word Wall" shortcut to save vocabulary and quotes from the current passage.

3. **Ask AI (`lib/screens/ask_ai_screen.dart`)**:
   - Grounded Q&A against the uploaded book (`POST /api/v1/ai/chat`).
   - Three reading modes: `Study`, `Research`, `Creative`.
   - Interaction helper chips: "What if…", "What happens next?", and "Explain themes".
   - Verifiable citation tags matching `[S#]` source chunks.
   - Spoiler guard boundary indicator (`spoiler_scope.reason`), ensuring answers never reveal future plot events.

4. **Visualize (`lib/screens/visualize_screen.dart`)**:
   - Dynamic **Character Map** extracted and cached by the backend (`/api/v1/books/{id}/relationships`).
   - On-demand **"Update"** action triggering grounded LLM character extraction up to the reader's current page/chapter (`/relationships/generate`).
   - **Characters view**: Character profile cards with role badges (protagonist, rival, mentor, etc.), descriptions, and direct connections.
   - **Relationships view**: All character-to-character edges showing relationship types, descriptive labels, and verbatim book evidence quotes.

5. **Progress (`lib/screens/progress_screen.dart`)**:
   - **Overview**: Reading progress percentage, consecutive daily reading streak (`current_streak` and `longest_streak`), and quick summaries.
   - **Word Wall**: Scoped to the current book, allowing readers to view, add, and delete saved literary vocabulary with meanings and quote sources (`/api/v1/books/{id}/words`).
   - **Achievements**: Live display of all 6 milestone badges (`/api/v1/achievements`): *Shelved your first book*, *Curious mind*, *The End*, *Building a habit*, *A week of reading*, and *Growing library*.
   - **Reading Log**: Calendar history of daily reading activity across all books (`/api/v1/reading-log`).

---

## 🚀 Running the App

### 1. Prerequisites
- [Flutter SDK](https://docs.flutter.dev/get-started/install) (Dart 3.10+)
- FastAPI backend running at `http://localhost:8000` (see `../backend/README.md`)

### 2. Dependency Installation
```bash
cd frontend
flutter pub get
```

### 3. Run on Web (Chrome / Edge)
```bash
flutter run -d chrome
```
> **WSL2 Note**: If running from inside WSL and mouse cursor disappears in Linux Chrome, run as a web server and open your native Windows browser:
> ```bash
> flutter run -d web-server --web-port=8080
> ```
> Then visit `http://localhost:8080` in Windows Chrome.

### 4. Run on Desktop (Linux / Windows)
- **Linux Desktop**:
  ```bash
  # Ensure Zenity is installed for native file dialogs
  sudo apt install -y zenity

  flutter run -d linux
  ```
- **Windows Desktop**:
  ```powershell
  flutter run -d windows
  ```

### 5. Run on Android Emulator
The Android emulator accesses your host machine at `10.0.2.2:8000`:
```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

---

## 🧪 Automated Tests

The test suite exercises all 5 tabs and validates that the frontend handles simulated backend responses:
```bash
flutter test
```
See `test/widget_test.dart` for the fake backend client mocking the API contract.
