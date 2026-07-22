PRAGMA foreign_keys = ON;

--------------------------------------------------------
-- ADMIN
--------------------------------------------------------

INSERT INTO users
(fullname, username, email, password, phone, role)
VALUES
(
'Administrator',
'admin',
'admin@parkflow.com',
'scrypt:32768:8:1$3DgbKhl5f680XgTm$b40182b80f41b39d8f99cdea025915e2393ac8656e5267ce7196ce7fb3049b2cf991709f3944111d5031aac1646de0d45e452b309f7f84928d05263a28f58edb',
'0600000000',
'ADMIN'
);

--------------------------------------------------------
-- GARDE
--------------------------------------------------------

INSERT INTO users
(fullname, username, email, password, phone, role)
VALUES
(
'Garde Principal',
'garde1',
'garde@parkflow.com',
'scrypt:32768:8:1$YLymflwabd9adYAY$ba28b0d02efa5c32e382a38768676ef6519a8cab58a15192ae93f4258745df3cfe6dfaee15371a49ff13948c4295229ddf8dd98e15d13ef9bc249f8505400204',
'0611111111',
'AGENT'
);

--------------------------------------------------------
-- ZONES
--------------------------------------------------------

INSERT INTO zones(name,description)
VALUES
('Zone A','Parking Principal');

INSERT INTO zones(name,description)
VALUES
('Zone B','Parking Secondaire');

INSERT INTO zones(name,description)
VALUES
('Personnel','Parking Employés');

--------------------------------------------------------
-- TYPES PARKING
--------------------------------------------------------

INSERT INTO parking_types
(name,duration_limit,price_24h,extra_hour_price,description)
VALUES
('VIP 24H',24,80,10,'Parking VIP');

INSERT INTO parking_types
(name,duration_limit,price_24h,extra_hour_price,description)
VALUES
('VIP +24H',24,80,15,'VIP longue durée');

INSERT INTO parking_types
(name,duration_limit,price_24h,extra_hour_price,description)
VALUES
('NORMAL 24H',24,40,5,'Parking normal');

INSERT INTO parking_types
(name,duration_limit,price_24h,extra_hour_price,description)
VALUES
('NORMAL +24H',24,40,8,'Parking longue durée');

INSERT INTO parking_types
(name,duration_limit,price_24h,extra_hour_price,description)
VALUES
('STAFF',0,0,0,'Personnel');

--------------------------------------------------------
-- BRANDS
--------------------------------------------------------

INSERT INTO brands(name) VALUES ('BMW');
INSERT INTO brands(name) VALUES ('Mercedes');
INSERT INTO brands(name) VALUES ('Audi');
INSERT INTO brands(name) VALUES ('Volkswagen');
INSERT INTO brands(name) VALUES ('Toyota');
INSERT INTO brands(name) VALUES ('Renault');
INSERT INTO brands(name) VALUES ('Peugeot');
INSERT INTO brands(name) VALUES ('Dacia');
INSERT INTO brands(name) VALUES ('Hyundai');
INSERT INTO brands(name) VALUES ('Kia');
INSERT INTO brands(name) VALUES ('Nissan');
INSERT INTO brands(name) VALUES ('Fiat');

--------------------------------------------------------
-- VEHICLE TYPES
--------------------------------------------------------

INSERT INTO vehicle_types(name) VALUES ('Berline');
INSERT INTO vehicle_types(name) VALUES ('SUV');
INSERT INTO vehicle_types(name) VALUES ('4x4');
INSERT INTO vehicle_types(name) VALUES ('Pick-up');
INSERT INTO vehicle_types(name) VALUES ('Camion');
INSERT INTO vehicle_types(name) VALUES ('Moto');
INSERT INTO vehicle_types(name) VALUES ('Mini Bus');

--------------------------------------------------------
-- COLORS
--------------------------------------------------------

INSERT INTO colors(name) VALUES ('Blanc');
INSERT INTO colors(name) VALUES ('Noir');
INSERT INTO colors(name) VALUES ('Gris');
INSERT INTO colors(name) VALUES ('Rouge');
INSERT INTO colors(name) VALUES ('Bleu');
INSERT INTO colors(name) VALUES ('Vert');
INSERT INTO colors(name) VALUES ('Jaune');
INSERT INTO colors(name) VALUES ('Argent');
INSERT INTO colors(name) VALUES ('Marron');

--------------------------------------------------------
-- PARKING PLACES
--------------------------------------------------------

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,1,'A001');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,1,'A002');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,2,'A003');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,3,'A004');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,3,'A005');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (1,4,'A006');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (2,3,'B001');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (2,3,'B002');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (2,4,'B003');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (2,4,'B004');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (3,5,'P001');

INSERT INTO parking_places(zone_id,parking_type_id,place_number)
VALUES (3,5,'P002');

--------------------------------------------------------
-- SETTINGS
--------------------------------------------------------

INSERT INTO settings
(
company_name,
airport_name,
airport_code,
address,
phone,
email,
logo,
currency
)
VALUES
(
'ParkFlow',
'Aéroport Essaouira Mogador',
'ESU',
'Essaouira, Maroc',
'+212 5 24 00 00 00',
'contact@parkflow.com',
'logo.png',
'MAD'
);

--------------------------------------------------------
-- NOTIFICATION
--------------------------------------------------------

INSERT INTO notifications
(title,message,type)
VALUES
(
'Bienvenue',
'Bienvenue dans Airport Smart Parking System.',
'SUCCESS'
);