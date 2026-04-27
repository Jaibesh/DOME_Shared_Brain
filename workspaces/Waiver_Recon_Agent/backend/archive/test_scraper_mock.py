from dotenv import load_dotenv
import os
import scraper
import waiver_link_storage

load_dotenv()

class MockSupabase:
    class MockTable:
        def select(self, *args): return self
        def gte(self, *args): return self
        def neq(self, *args): return self
        def execute(self):
            class MockResponse:
                data = [{'tw_confirmation': 'TEST', 'mpwr_number': 'CO-PA3-578', 'polaris_complete': 0, 'polaris_expected': 2}]
            return MockResponse()
        def update(self, *args): return self
        def eq(self, *args): return self
    def table(self, *args): return self.MockTable()

scraper.get_supabase = lambda: MockSupabase()
scraper.run_mpowr_scraper(os.getenv('MPOWR_EMAIL'), os.getenv('MPOWR_PASSWORD'))
