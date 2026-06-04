import unittest

from aria_core.drive_workspace import DOC_MIME, FOLDER_MIME, DriveWorkspace


class FakeCall:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value() if callable(self.value) else self.value


class FakeFiles:
    def __init__(self):
        self.files = {}
        self.next_id = 1

    def list(self, q="", **kwargs):
        if f"mimeType='{FOLDER_MIME}'" in q:
            folders = [file for file in self.files.values() if file["mimeType"] == FOLDER_MIME and not file.get("trashed")]
            return FakeCall({"files": folders})
        if f"mimeType='{DOC_MIME}'" in q:
            docs = [file for file in self.files.values() if file["mimeType"] == DOC_MIME and not file.get("trashed")]
            return FakeCall({"files": docs})
        return FakeCall({"files": []})

    def create(self, body, fields=""):
        def _create():
            file_id = f"file_{self.next_id}"
            self.next_id += 1
            item = {
                "id": file_id,
                "name": body["name"],
                "mimeType": body["mimeType"],
                "parents": body.get("parents", []),
                "trashed": False,
                "webViewLink": f"https://docs.example/{file_id}",
                "modifiedTime": "now",
            }
            self.files[file_id] = item
            return item

        return FakeCall(_create)

    def get(self, fileId, fields=""):
        return FakeCall(self.files[fileId])

    def update(self, fileId, body, fields=""):
        def _update():
            self.files[fileId].update(body)
            return self.files[fileId]

        return FakeCall(_update)


class FakeDrive:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


class FakeDocuments:
    def __init__(self):
        self.text = {}

    def batchUpdate(self, documentId, body):
        def _update():
            text = body["requests"][0]["insertText"]["text"]
            self.text[documentId] = text
            return {}

        return FakeCall(_update)

    def get(self, documentId):
        text = self.text.get(documentId, "")
        return FakeCall(
            {
                "title": "Doc",
                "body": {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": text}}]}},
                    ]
                },
            }
        )


class FakeDocs:
    def __init__(self, documents):
        self._documents = documents

    def documents(self):
        return self._documents


class FakeGoogle:
    def __init__(self):
        self.files = FakeFiles()
        self.documents = FakeDocuments()
        self.drive = FakeDrive(self.files)
        self.docs = FakeDocs(self.documents)

    def _get_user_drive_docs(self):
        return None, None


class DriveWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_folder_and_document_inside_aria(self):
        google = FakeGoogle()
        workspace = DriveWorkspace(google)

        created = await workspace.create_document("Plan", "Contenido")
        docs = await workspace.list_documents()
        read = await workspace.read_document(created["documentId"])

        self.assertEqual(created["folder"], "Aria")
        self.assertEqual(len(docs), 1)
        self.assertEqual(read["content"], "Contenido")

    async def test_trash_document_marks_trashed(self):
        google = FakeGoogle()
        workspace = DriveWorkspace(google)

        created = await workspace.create_document("Plan", "Contenido")
        result = await workspace.trash_document(created["documentId"])

        self.assertEqual(result["status"], "trashed")
        self.assertTrue(google.files.files[created["documentId"]]["trashed"])


if __name__ == "__main__":
    unittest.main()
