create table if not exists spent(nonce text primary key, tx text unique, payer text, at real, settled int default 0);
