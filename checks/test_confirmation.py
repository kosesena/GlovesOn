"""Draft guard tests without database resets or real ERP writes."""
import hashlib
import unittest
from unittest.mock import AsyncMock, patch

from gateway import confirmation, main


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.payload={'material':'4711','quantity':20,'bin':'A-03-02','allow_duplicate':False}
        self.row={'state':'pending','expires_at':200,'token_hash':hashlib.sha256(b'token').hexdigest(),
                  'operation':'receipt','payload':confirmation.canonical(self.payload)}
    def check(self,**changes):
        args=dict(row=self.row,token='token',operation='receipt',payload=self.payload,response='confirm',now=100)
        args.update(changes)
        return confirmation.rejection(**args)
    def test_valid_exact_draft(self):self.assertIsNone(self.check())
    def test_expired_or_consumed(self):
        self.assertIsNotNone(self.check(now=200))
        self.assertIsNotNone(self.check(row={**self.row,'state':'consumed'}))
    def test_quantity_destination_and_duplicate_changes_rejected(self):
        for field,value in [('quantity',12),('bin','B-02'),('allow_duplicate',True)]:
            with self.subTest(field=field):
                self.assertIsNotNone(self.check(payload={**self.payload,field:value}))
    def test_wrong_token_or_operation(self):
        self.assertIsNotNone(self.check(token='other-session-token'))
        self.assertIsNotNone(self.check(operation='reversal'))
    def test_ambiguous_or_missing_consent_rejected(self):
        for response in [None,'','yes but twelve','no','okay','yes, actually no',True]:
            with self.subTest(response=response):
                self.assertIsNotNone(self.check(response=response))
    def test_no_draft(self):self.assertIsNotNone(self.check(row=None))

class WriteRouteTests(unittest.IsolatedAsyncioTestCase):
    def fake_sap(self):
        sap=AsyncMock()
        sap.get_stock.return_value=[{'MaterialBaseUnit':'EA','StorageBin':'A-03-02','StorageLocation':'0001'}]
        sap.get_description.return_value={'ProductDescription':'Hex bolt M8'}
        return sap
    async def test_preparation_emits_details_and_never_posts(self):
        sap=self.fake_sap()
        ctx=main.event_scope.set('scope-a')
        try:
            with patch.object(main.confirmation,'invalidate'), patch.object(main,'sap',return_value=sap), patch.object(main.confirmation,'prepare',return_value='draft') as prepare, patch.object(main,'publish') as publish:
                r=await main.prepare_receipt({'material':'4711','quantity':20},main.TOOL_SHARED_SECRET)
                self.assertTrue(r['prepared'])
                self.assertEqual(r['details']['MENGE'],20)
                self.assertEqual(prepare.call_args.args[0],'scope-a')
                self.assertEqual(publish.call_args.args[0],'write_draft')
                sap.post_material_document.assert_not_awaited()
        finally:
            main.event_scope.reset(ctx)
    async def test_rejected_draft_cannot_reach_erp_write(self):
        sap=self.fake_sap()
        with patch.object(main,'sap',return_value=sap),patch.object(main,'publish'):
            r=await main.post_goods_receipt({'material':'4711','quantity':20},main.TOOL_SHARED_SECRET)
            self.assertFalse(r['posted'])
            sap.post_material_document.assert_not_awaited()
    async def test_invalid_storage_location_not_silently_replaced(self):
        sap=self.fake_sap()
        with patch.object(main,'publish'), patch.object(main.confirmation,'invalidate'), patch.object(main,'sap',return_value=sap),patch.object(main.confirmation,'prepare') as prepare:
            r=await main.prepare_receipt({'material':'4711','quantity':20,'storage_location':'wrong'},main.TOOL_SHARED_SECRET)
            self.assertFalse(r['posted'])
            prepare.assert_not_called()
            sap.post_material_document.assert_not_awaited()
    async def test_reversal_without_draft_does_not_post(self):
        sap=self.fake_sap()
        sap.list_documents.return_value=[{'MaterialDocument':'123','GoodsMovementType':'501','Material':'4711',
            'Plant':'1000','StorageLocation':'0001','StorageBin':'A-03-02','EntryUnit':'EA','QuantityInEntryUnit':'20'}]
        with patch.object(main,'sap',return_value=sap),patch.object(main,'publish'):
            r=await main.reverse_goods_receipt({'document':'123'},main.TOOL_SHARED_SECRET)
            self.assertFalse(r['reversed'])
            sap.post_material_document.assert_not_awaited()
