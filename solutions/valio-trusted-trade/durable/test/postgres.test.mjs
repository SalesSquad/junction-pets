import test from 'node:test';
import assert from 'node:assert/strict';

test('real PostgreSQL multi-process durability and crash-before-ACK',
  {skip:!process.env.VALIO_TEST_DATABASE_URL?'BLOCKED: no disposable VALIO_TEST_DATABASE_URL in this executor':false,timeout:180_000},async()=>{
    const {runChaosLab}=await import('../smoke.mjs');
    const r=await runChaosLab({connectionString:process.env.VALIO_TEST_DATABASE_URL,requestCount:100,workerCount:8});
    assert.equal(r.postCommitCrashObserved,true);
    assert.equal(r.crashReplayed,true);
    assert.equal(r.sealedBatchRefusal,true);
    assert.equal(r.refundRaceSingleWinner,true);
    assert.equal(r.outboxDeleteRefusal,true);
    assert.equal(r.outboxRetargetRefusal,true);
    assert.equal(r.outboxTruncateRefusal,true);
    assert.equal(r.verified.balanced,true);
    assert.equal(r.verified.matching,true);
    assert.equal(r.verified.nonnegative,true);
    assert.equal(r.verified.batches,203);
    assert.equal(r.verified.outboxEvents,203);
  });

test('PostgreSQL freezes replay commands and settlement terms while allowing one exact compensating refund',
  {skip:!process.env.VALIO_TEST_DATABASE_URL?'BLOCKED: no disposable VALIO_TEST_DATABASE_URL in this executor':false,timeout:30_000},async()=>{
    const {randomUUID}=await import('node:crypto');
    const {default:pg}=await import('pg');
    const {Pool}=pg;
    const {createLabSchema,seedAccounts,settleDemoPayment,refundDemoPayment,auditLab}=await import('../index.mjs');
    const schema='j26_guards_'+randomUUID().replaceAll('-','');
    const pool=new Pool({connectionString:process.env.VALIO_TEST_DATABASE_URL,max:4});
    let created=false;
    try{
      await createLabSchema(pool,schema);created=true;
      await seedAccounts(pool,{schema,buyerFundsCents:1000,suppliers:['farm-a','farm-b']});
      const input={schema,orderId:'guardOrderA',idempotencyKey:'guard_payment_A',
        buyerAccount:'demo:buyer:wallet',totalCents:100,
        allocations:[{supplierId:'farm-a',amountCents:60},{supplierId:'farm-b',amountCents:40}],
        verifiedQuoteBodyDigest:'a'.repeat(64),approvedProposalDigest:'b'.repeat(64)};
      const payment=await settleDemoPayment(pool,input);
      const refused=(sql,params=[])=>assert.rejects(pool.query(sql,params),
        e=>e.code==='23514'&&/IMMUTABLE_LEDGER_COMMANDS|IMMUTABLE_SETTLEMENT_TERMS/.test(e.message));
      for(const expression of [
        "result='{}'::jsonb","intent_digest='forged'","kind='SIMULATED_REFUND'",
        "idempotency_key='another_key'","created_at=created_at+interval '1 second'"
      ])await refused(`UPDATE "${schema}".ledger_commands SET ${expression} WHERE idempotency_key=$1`,[input.idempotencyKey]);
      await refused(`DELETE FROM "${schema}".ledger_commands WHERE idempotency_key=$1`,[input.idempotencyKey]);
      await refused(`TRUNCATE "${schema}".ledger_commands`);
      for(const expression of [
        'total_cents=1',"allocations='[]'::jsonb","payment_digest='forged'",
        "order_id='forgedOrder'","created_at=created_at+interval '1 second'",
        "buyer_account='demo:supplier:farm-a:wallet'"
      ])await refused(`UPDATE "${schema}".demo_settlements SET ${expression} WHERE order_id=$1`,[input.orderId]);
      await refused(`UPDATE "${schema}".demo_settlements SET payment_batch_id=$1 WHERE order_id=$2`,[randomUUID(),input.orderId]);
      await refused(`DELETE FROM "${schema}".demo_settlements WHERE order_id=$1`,[input.orderId]);
      await refused(`TRUNCATE "${schema}".demo_settlements`);
      await assert.rejects(pool.query(`UPDATE "${schema}".demo_settlements SET refund_batch_id=$1 WHERE order_id=$2`,
        [payment.batchId,input.orderId]),e=>e.code==='23514'&&/INVALID_SETTLEMENT_REFUND_LINK/.test(e.message));

      // A schema-qualified caller need not have the lab in search_path.
      // Build balanced counterfeit batches, then prove final linkage rejects
      // a wrong order, wrong inverse allocation and absent atomic outbox.
      const forgedRefund=async({orderId=input.orderId,buyerDelta=100,supplierA=-60,supplierB=-40,outbox=true,appendAfter=false}={})=>{
        const c=await pool.connect();const batchId=randomUUID();
        try{
          await c.query('BEGIN');
          await c.query(`INSERT INTO "${schema}".ledger_batches(batch_id,order_id,kind,intent_digest) VALUES($1,$2,'SIMULATED_REFUND',$3)`,[batchId,orderId,'c'.repeat(64)]);
          for(const [account,delta] of [['demo:buyer:wallet',buyerDelta],['demo:supplier:farm-a:wallet',supplierA],['demo:supplier:farm-b:wallet',supplierB]]){
            await c.query(`INSERT INTO "${schema}".ledger_entries(batch_id,account_id,delta_cents) VALUES($1,$2,$3)`,[batchId,account,delta]);
          }
          await c.query(`UPDATE "${schema}".demo_settlements SET refund_batch_id=$1 WHERE order_id=$2`,[batchId,input.orderId]);
          if(appendAfter){
            await c.query(`INSERT INTO "${schema}".wallet_accounts(account_id,opening_balance_cents,balance_cents) VALUES('demo:extra:a',0,0),('demo:extra:b',0,0)`);
            await c.query(`INSERT INTO "${schema}".ledger_entries(batch_id,account_id,delta_cents) VALUES($1,'demo:extra:a',1),($1,'demo:extra:b',-1)`,[batchId]);
          }
          if(outbox)await c.query(`INSERT INTO "${schema}".ledger_outbox(event_id,batch_id,event_kind,payload) VALUES($1,$2,'SIMULATED_REFUNDED',$3::jsonb)`,
            [randomUUID(),batchId,JSON.stringify({orderId,batchId,originalBatchId:payment.batchId,totalCents:100,currency:'EUR'})]);
          await c.query('COMMIT');
        }catch(e){await c.query('ROLLBACK');throw e;}
        finally{c.release();}
      };
      await assert.rejects(forgedRefund({orderId:'wrongOrder'}),e=>e.code==='23514'&&/INVALID_SETTLEMENT_REFUND_LINK/.test(e.message));
      await assert.rejects(forgedRefund({buyerDelta:90,supplierA:-60,supplierB:-30}),e=>e.code==='23514'&&/INVALID_SETTLEMENT_REFUND_ENTRIES/.test(e.message));
      await assert.rejects(forgedRefund({outbox:false}),e=>e.code==='23514'&&/INVALID_SETTLEMENT_REFUND_LINK/.test(e.message));
      await assert.rejects(forgedRefund({appendAfter:true}),e=>e.code==='23514'&&/INVALID_SETTLEMENT_REFUND_ENTRIES/.test(e.message));
      const replay=await settleDemoPayment(pool,input);
      assert.equal(replay.idempotentReplay,true);assert.equal(replay.batchId,payment.batchId);
      const refundInput={schema,orderId:input.orderId,idempotencyKey:'guard_refund_AA'};
      const refund=await refundDemoPayment(pool,refundInput);
      assert.equal(refund.status,'SIMULATED_REFUNDED');
      assert.equal((await refundDemoPayment(pool,refundInput)).batchId,refund.batchId);
      assert.equal((await refundDemoPayment(pool,refundInput)).idempotentReplay,true);
      await assert.rejects(refundDemoPayment(pool,{...refundInput,idempotencyKey:'guard_refund_new'}),e=>e.code==='ORDER_ALREADY_REFUNDED');
      await refused(`UPDATE "${schema}".demo_settlements SET refund_batch_id=NULL WHERE order_id=$1`,[input.orderId]);
      await refused(`UPDATE "${schema}".demo_settlements SET refund_batch_id=refund_batch_id WHERE order_id=$1`,[input.orderId]);
      const audit=await auditLab(pool,schema);
      assert.equal(audit.balanced,true);assert.equal(audit.matching,true);assert.equal(audit.nonnegative,true);
      assert.equal(audit.batches,2);assert.equal(audit.outboxEvents,2);assert.equal(audit.refunds,1);
    }finally{
      if(created)await pool.query(`DROP SCHEMA "${schema}" CASCADE`);
      await pool.end();
    }
  });
