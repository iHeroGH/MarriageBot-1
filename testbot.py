import asyncio
import random
import string
from datetime import datetime as dt
import enum

import aioneo4j
import discord
from discord.ext import commands

from cogs import utils


bot = commands.Bot(command_prefix='m,')
bot.neo4j = aioneo4j.Neo4j(host='127.0.0.1', port=7474, user='neo4j', password='compression', database='marriagebottest')


class RelationshipType(enum.Enum):
    MARRIED_TO = 1
    PARENT_OF = 2


class FamilyRelationship(object):

    def __init__(self, user:int, relationship:RelationshipType, user2:int):
        self.user = user
        self.relationship = relationship
        self.user2 = user2

    def __eq__(self, other):
        return all([
            isinstance(other, self.__class__),
            self.user == other.user,
            self.relationship == other.relationship,
            self.user2 == other.user2
        ])


def get_random_string(k=10):
    return ''.join(random.choices(string.ascii_letters, k=10))


async def is_related(user, user2):
    data = await bot.neo4j.cypher(
        r"""MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0}), (m:FamilyTreeMember {user_id: $user_id, guild_id: 0})
        CALL gds.alpha.shortestPath.stream({
            nodeProjection: 'FamilyTreeMember',
            relationshipWeightProperty: null,
            relationshipProjection: {
                MARRIED_TO: {type: 'MARRIED_TO', orientation: 'UNDIRECTED'},
                CHILD_OF: {type: 'CHILD_OF', orientation: 'UNDIRECTED'},
                PARENT_OF: {type: 'PARENT_OF', orientation: 'UNDIRECTED'}
            }, startNode: n, endNode: m
        }) YIELD nodeId
        RETURN gds.util.asNode(nodeId)""",
        author_id=user.id, user_id=user2.id
    )
    matches = data['results'][0]['data']
    return matches


async def get_tree_root_user_id(user):
    data = await bot.neo4j.cypher(
        r"""MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:CHILD_OF*]->(m:FamilyTreeMember {guild_id: 0}) RETURN m""",
        user_id=user.id
    )
    matches = data['results'][0]['data']
    if matches:
        return matches[-1]['row'][0]['user_id']
    return user.id


async def get_tree_expanded_from_root(root_user):
    output_data = []
    processed_users = []
    uids = [root_user.id]
    while uids:
        data = await bot.neo4j.cypher(
            r"""UNWIND $user_ids AS X MATCH (n:FamilyTreeMember {user_id: X, guild_id: 0})-[r:PARENT_OF|MARRIED_TO]->(m:FamilyTreeMember {guild_id: 0}) RETURN n, type(r), m""",
            user_ids=uids
        )
        processed_users.extend(uids)
        uids.clear()
        for return_value in data['results'][0]['data']:
            n, r, m = return_value['row']
            relationship = FamilyRelationship(n['user_id'], RelationshipType[r], m['user_id'])
            if relationship not in output_data:
                output_data.append(relationship)
            if n['user_id'] not in processed_users:
                uids.append(n['user_id'])
            if m['user_id'] not in processed_users:
                uids.append(m['user_id'])
    return output_data


async def get_all_family_member_nodes(user):
    data = await bot.neo4j.cypher(
        r"""MATCH (u:FamilyTreeMember {user_id: $user_id, guild_id: 0})
        CALL gds.alpha.shortestPath.deltaStepping.stream({
            startNode: u,
            nodeProjection: 'FamilyTreeMember',
            relationshipProjection: {
                MARRIED_TO: {type: 'MARRIED_TO', orientation: 'NATURAL'},
                CHILD_OF: {type: 'CHILD_OF', orientation: 'NATURAL'},
                PARENT_OF: {type: 'PARENT_OF', orientation: 'NATURAL'}
            },
            delta: 1.0
        }) YIELD nodeId, distance
        WHERE distance < gds.util.infinity()
        RETURN gds.util.asNode(nodeId), distance""",
        user_id=user.id
    )
    matches = data['results'][0]['data']
    return matches


async def get_blood_family_member_nodes(user):
    data = await bot.neo4j.cypher(
        r"""MATCH (u:FamilyTreeMember {user_id: $user_id, guild_id: 0})
        CALL gds.alpha.shortestPath.deltaStepping.stream({
            startNode: u,
            nodeProjection: 'FamilyTreeMember',
            relationshipProjection: {
                MARRIED_TO: {type: 'MARRIED_TO', orientation: 'NATURAL'},
                PARENT_OF: {type: 'PARENT_OF', orientation: 'NATURAL'}
            },
            delta: 1.0
        }) YIELD nodeId, distance
        WHERE distance < gds.util.infinity()
        RETURN gds.util.asNode(nodeId), distance""",
        user_id=user.id
    )
    matches = data['results'][0]['data']
    return matches


async def get_family_size(user):
    return len(await get_all_family_member_nodes(user))


async def get_blood_family_size(user):
    return len(await get_blood_family_member_nodes(user))


async def get_relationship(user, user2):
    formatable_string = "(:FamilyTreeMember {{user_id: {0}, guild_id: 0}})"
    tree_member_nodes = []
    uids = []
    data = await is_related(user, user2)
    if not data:
        return "nonesadjkhf"

    # Create all the nodes to match
    for row in data:
        user_id = row['row'][0]['user_id']
        tree_member_nodes.append(formatable_string.format(user_id))

    # Create the cypher
    cypher = "MATCH "
    for tree_member in tree_member_nodes:
        cypher += tree_member
        if tree_member == tree_member_nodes[-1]:
            continue
        uids.append(get_random_string())
        cypher += f"-[{uids[-1]}]->"
    typed_uids = [f"type({i})" for i in uids]
    cypher += f" RETURN {', '.join(typed_uids)}"
    data = await bot.neo4j.cypher(cypher)

    # And this is the actual result
    matches = data['results'][0]['data'][0]['row']
    return matches


class FamilyMember(object):

    def __init__(self, user_id:int):
        self.user_id = user_id
        self.parent = None
        self.children = []
        self.partner = None
        self._relationship_string = None

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.user_id == other.user_id

    @property
    def relationship_string(self):
        if self._relationship_string:
            return self._relationship_string
        if self.partner:
            relationship_list = sorted([self.user_id, self.partner.user_id])
            self._relationship_string = f"r{relationship_list[1]}_{relationship_list[0]}"
        else:
            self._relationship_string = f"{self.user_id}"
        return self._relationship_string

    def expand_downwards_to_dot(self) -> str:
        """Expand this tree downwards into a dot script"""

        added_users = 0
        output_string = (
            """digraph{rankdir="LR";"""
            """node [shape=box, fontcolor="#FFFFFF", color="#000000", fillcolor="#000000", style=filled];"""
            """edge [dir=none, color="#000000"];"""
        )

        # Loop through every user and append their partners
        this_rank_of_users = [self]
        for user in this_rank_of_users.copy():
            if user.partner:
                this_rank_of_users.append(user.partner)

        # Add these users to the output string
        while this_rank_of_users:

            # Add every user and user label
            for user in this_rank_of_users:
                output_string += f"""{user.user_id}[label="{user.user_id}"];"""
                added_users += 1

            # Join married users together
            added_relationships = []
            output_string += "{rank=same;"
            for user in this_rank_of_users:
                if user.partner:
                    if user.relationship_string not in added_relationships and user.relationship_string.split("_")[-1] == str(user.user_id):
                        output_string += f"{user.user_id} -> {user.relationship_string} -> {user.partner.user_id};"
                        output_string += f"""{user.relationship_string}[shape=circle, label="", height=0.001, width=0.001];"""
                        added_relationships.append(user._relationship_string)
            output_string += "}"

            # Join parents to their child root node
            added_relationships = []
            for user in this_rank_of_users:
                if not user.children:
                    continue
                if user.relationship_string not in added_relationships:
                    output_string += f"{user.relationship_string} -> h{user.relationship_string};"
                    added_relationships.append(user._relationship_string)

            # Join children to their parent root node
            added_relationships = []
            for user in this_rank_of_users:
                for child in user.children:
                    output_string += f"h{user.relationship_string} -> {child.user_id};"
                if user.children and user._relationship_string not in added_relationships:
                    output_string += f"""h{user.relationship_string}[shape=circle, label="", height=0.001, width=0.001];"""
                    added_relationships.append(user._relationship_string)

            # Change the list of users to be the current rank's children and their partners
            old_rank_of_users = this_rank_of_users.copy()
            this_rank_of_users = []
            [this_rank_of_users.extend(i.children) for i in old_rank_of_users]
            for user in this_rank_of_users.copy():
                if user.partner:
                    this_rank_of_users.append(user.partner)

        # Return stuff
        output_string += "}"
        return output_string, added_users

    @classmethod
    def get_family_from_cypher(cls, cypher_output:list, root_user_id:int=None):
        """"""

        # Make it into a nice lot of objects
        family_objects = {}
        for relationship in cypher_output:
            node = family_objects.get(relationship.user, FamilyMember(relationship.user))
            family_objects[relationship.user] = node
            if relationship.relationship == RelationshipType.MARRIED_TO:
                node.partner = family_objects.get(relationship.user2, FamilyMember(relationship.user2))
                node.partner.partner = node
                family_objects[relationship.user2] = node.partner
            elif relationship.relationship == RelationshipType.PARENT_OF:
                new_object = family_objects.get(relationship.user2, FamilyMember(relationship.user2))
                if new_object not in node.children:
                    node.children.append(new_object)
                    node.children[-1].parent = node
                    family_objects[relationship.user2] = node.children[-1]
        return family_objects.get(root_user_id or list(family_objects.keys())[0])


class FamilyCommands(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(cls=utils.Command)
    async def partner(self, ctx:utils.Context, user_id:utils.converters.UserID=None):
        """Tells you who a given user's partner is"""

        user_id = user_id or ctx.author.id
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:MARRIED_TO]->(m:FamilyTreeMember) RETURN m",
            user_id=user_id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send(f"<@{user_id}> isn't married error.", allowed_mentions=discord.AllowedMentions(users=False))
        return await ctx.send(f"<@{user_id}> is married to <@{matches[0]['row'][0]['user_id']}>.", allowed_mentions=discord.AllowedMentions(users=False))

    @commands.command(cls=utils.Command)
    async def marry(self, ctx:utils.Context, user:discord.Member):
        """Marries to you another user"""

        # Check exemptions
        if user.bot or user == ctx.author:
            return await ctx.send("Invalid user error.")

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {guild_id: 0})-[:MARRIED_TO]->(:FamilyTreeMember) WHERE n.user_id in [$author_id, $user_id] RETURN n",
            author_id=ctx.author.id, user_id=user.id
        )
        matches = data['results'][0]['data']
        if matches:
            if matches[0]['row'][0]['user_id'] == ctx.author.id:
                return await ctx.send("You're already married error.")
            return await ctx.send("They're already married error.")

        # See if they're already related
        if await is_related(ctx.author, user):
            return await ctx.send("You're already related error.")

        # Add them to the db
        data = await self.bot.neo4j.cypher(
            r"""MERGE (n:FamilyTreeMember {user_id: $author_id, guild_id: 0}) MERGE (m:FamilyTreeMember {user_id: $user_id, guild_id: 0})
            MERGE (n)-[:MARRIED_TO {timestamp: $timestamp}]->(m)-[:MARRIED_TO {timestamp: $timestamp}]->(n)""",
            author_id=ctx.author.id, user_id=user.id, timestamp=dt.utcnow().timestamp()
        )
        return await ctx.send("Added to database.")

    @commands.command(cls=utils.Command)
    async def divorce(self, ctx:utils.Context):
        """Divorces you form your partner"""

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0})-[:MARRIED_TO]->(m:FamilyTreeMember) RETURN m",
            author_id=ctx.author.id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send("You're not married error.")
        partner_id = matches[0]['row'][0]['user_id']

        # Remove them from the db
        data = await self.bot.neo4j.cypher(
            r"""MATCH (:FamilyTreeMember {user_id: $author_id, guild_id: 0})<-[r:MARRIED_TO]->(:FamilyTreeMember {user_id: $partner_id}) DELETE r""",
            author_id=ctx.author.id, partner_id=partner_id
        )
        return await ctx.send("Deleted from database.")

    @commands.command(cls=utils.Command)
    async def children(self, ctx:utils.Context, user:discord.Member=None):
        """Gives you a list of someone's children"""

        user = user or ctx.author
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:PARENT_OF]->(m:FamilyTreeMember) RETURN m",
            user_id=user.id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send(f"{user.mention} has no children error.", allowed_mentions=discord.AllowedMentions(users=False))
        uids = []
        for row in matches:
            uids.append(f"<@{row['row'][0]['user_id']}>")
        return await ctx.send(f"{user.mention} is parent of {', '.join(uids)}.", allowed_mentions=discord.AllowedMentions(users=False))

    @commands.command(cls=utils.Command)
    async def parent(self, ctx:utils.Context, user_id:utils.converters.UserID=None):
        """Tells you who a given user's parent is"""

        user_id = user_id or ctx.author.id
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:CHILD_OF]->(m:FamilyTreeMember) RETURN m",
            user_id=user_id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send(f"<@{user_id}> has no parent error.", allowed_mentions=discord.AllowedMentions(users=False))
        return await ctx.send(f"<@{user_id}> is the child of to <@{matches[0]['row'][0]['user_id']}>.", allowed_mentions=discord.AllowedMentions(users=False))

    @commands.command(cls=utils.Command)
    async def adopt(self, ctx:utils.Context, user:discord.Member):
        """Adopt a user"""

        # Check exemptions
        if user.bot or user == ctx.author:
            return await ctx.send("Invalid user error.")

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:CHILD_OF]->(m:FamilyTreeMember) RETURN m",
            user_id=user.id
        )
        matches = data['results'][0]['data']
        if matches:
            return await ctx.send("They have a parent error.")

        # See if they're already related
        if await is_related(ctx.author, user):
            return await ctx.send("You're already related error.")

        # Add them to the db
        data = await self.bot.neo4j.cypher(
            r"""MERGE (n:FamilyTreeMember {user_id: $author_id, guild_id: 0}) MERGE (m:FamilyTreeMember {user_id: $user_id, guild_id: 0})
            MERGE (n)-[:PARENT_OF {timestamp: $timestamp}]->(m)-[:CHILD_OF {timestamp: $timestamp}]->(n)""",
            author_id=ctx.author.id, user_id=user.id, timestamp=dt.utcnow().timestamp()
        )
        return await ctx.send("Added to database.")

    @commands.command(cls=utils.Command)
    async def makeparent(self, ctx:utils.Context, user:discord.Member):
        """Make a user your parent"""

        # Check exemptions
        if user.bot or user == ctx.author:
            return await ctx.send("Invalid user error.")

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $user_id, guild_id: 0})-[:PARENT_OF]->(m:FamilyTreeMember) RETURN m",
            user_id=user.id
        )
        matches = data['results'][0]['data']
        if matches:
            return await ctx.send("You have a parent error.")

        # See if they're already related
        if await is_related(ctx.author, user):
            return await ctx.send("You're already related error.")

        # Add them to the db
        data = await self.bot.neo4j.cypher(
            r"""MERGE (n:FamilyTreeMember {user_id: $author_id, guild_id: 0}) MERGE (m:FamilyTreeMember {user_id: $user_id, guild_id: 0})
            MERGE (n)-[:CHILD_OF {timestamp: $timestamp}]->(m)-[:PARENT_OF {timestamp: $timestamp}]->(n)""",
            author_id=ctx.author.id, user_id=user.id, timestamp=dt.utcnow().timestamp()
        )
        return await ctx.send("Added to database.")

    @commands.command(cls=utils.Command)
    async def emancipate(self, ctx:utils.Context):
        """Leave your parent"""

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0})-[:CHILD_OF]->(m:FamilyTreeMember) RETURN m",
            author_id=ctx.author.id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send("You're not adopted error.")
        parent_id = matches[0]['row'][0]['user_id']

        # Remove them from the db
        data = await self.bot.neo4j.cypher(
            r"""MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0})-[r:CHILD_OF]->(:FamilyTreeMember)-[t:PARENT_OF]->(n) DELETE r, t""",
            author_id=ctx.author.id, parent_id=parent_id
        )
        return await ctx.send("Deleted from database.")

    @commands.command(cls=utils.Command)
    async def disown(self, ctx:utils.Context, user_id:utils.converters.UserID):
        """Leave your parent"""

        # See if they're already married
        data = await self.bot.neo4j.cypher(
            r"MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0})-[:PARENT_OF]->(m:FamilyTreeMember {user_id: $user_id}) RETURN m",
            author_id=ctx.author.id, user_id=user_id
        )
        matches = data['results'][0]['data']
        if not matches:
            return await ctx.send("You're not their parent error.")
        child_id = matches[0]['row'][0]['user_id']

        # Remove them from the db
        data = await self.bot.neo4j.cypher(
            r"""MATCH (n:FamilyTreeMember {user_id: $author_id, guild_id: 0})-[r:PARENT_OF]->(:FamilyTreeMember)-[t:CHILD_OF]->(n) DELETE r, t""",
            author_id=ctx.author.id, parent_id=child_id
        )
        return await ctx.send("Deleted from database.")

    @commands.command(cls=utils.Command)
    async def related(self, ctx:utils.Context, user:discord.Member):
        """Tells you if you're related to a user"""

        if await is_related(ctx.author, user):
            return await ctx.send("Yes, you are related.")
        return await ctx.send("No, you aren't related.")

    @commands.command(cls=utils.Command)
    async def relationship(self, ctx:utils.Context, user:discord.Member):
        """Tells you if you're related to a user"""

        return await ctx.send(await get_relationship(ctx.author, user))

    @commands.command(cls=utils.Command)
    async def familysize(self, ctx:utils.Context, user_id:utils.converters.UserID=None):
        """Tells you if you're related to a user"""

        user_id = user_id or ctx.author.id
        blood_size = await get_blood_family_size(discord.Object(user_id))
        full_size = await get_family_size(discord.Object(user_id))
        return await ctx.send(f"<@{user_id}>'s family size is {blood_size} blood relatives and {full_size} general relatives.", allowed_mentions=discord.AllowedMentions(users=False))

    @commands.command(cls=utils.Command)
    async def tree(self, ctx:utils.Context, user_id:utils.converters.UserID=None):
        """Tells you if you're related to a user"""

        # Get dot script
        user_id = user_id or ctx.author.id
        start_time = dt.utcnow()
        root_user_id = await get_tree_root_user_id(discord.Object(user_id))
        root_found_time = dt.utcnow()
        family = await get_tree_expanded_from_root(discord.Object(root_user_id))
        family_spanned_time = dt.utcnow()
        root_user = FamilyMember.get_family_from_cypher(family, root_user_id=root_user_id)
        cached_time = dt.utcnow()
        dot, user_count = root_user.expand_downwards_to_dot()
        dot_generated_time = dt.utcnow()

        # Write to file
        try:
            with open(f'{ctx.author.id}.gz', 'w', encoding='utf-8') as a:
                a.write(dot)
        except Exception as e:
            self.logger.error(f"Could not write to {self.bot.config['tree_file_location']}/{ctx.author.id}.gz")
            raise e
        written_to_file_time = dt.utcnow()

        # Convert to an image
        dot_process = await asyncio.create_subprocess_exec(*[
            'dot', '-Tpng', f'{ctx.author.id}.gz', '-o', f'{ctx.author.id}.png', '-Gcharset=UTF-8',
        ])
        try:
            await asyncio.wait_for(dot_process.wait(), 10)
        except asyncio.TimeoutError:
            pass
        try:
            dot_process.kill()
        except ProcessLookupError:
            pass  # It already died
        except Exception as e:
            raise e
        output_as_image_time = dt.utcnow()

        # Generate debug string
        output_string = [
            f"Time taken to get root: {(root_found_time - start_time).total_seconds() * 1000:.2f}ms",
            f"Time taken to span family: {(family_spanned_time - root_found_time).total_seconds() * 1000:.2f}ms",
            f"Time taken to cache users: {(cached_time - family_spanned_time).total_seconds() * 1000:.2f}ms",
            f"Time taken to generate dot: {(dot_generated_time - cached_time).total_seconds() * 1000:.2f}ms",
            f"Time taken to write to file: {(written_to_file_time - dot_generated_time).total_seconds() * 1000:.2f}ms",
            f"Time taken to interpret dot: {(output_as_image_time - written_to_file_time).total_seconds() * 1000:.2f}ms",
            f"**Total time taken: {(dt.utcnow() - start_time).total_seconds() * 1000:.2f}ms**",
        ]

        # Output file
        file = discord.File(f"{ctx.author.id}.png", filename="tree.png")
        return await ctx.send('\n'.join(output_string), file=file)

    @commands.command(cls=utils.Command)
    @commands.is_owner()
    async def cypher(self, ctx:utils.Context, *, cypher:str):
        """Leave your parent"""

        # See if they're already married
        await ctx.send("running")
        try:
            data = await self.bot.neo4j.cypher(cypher)
        except aioneo4j.errors.ClientError as e:
            return await ctx.send(str(e))
        return await ctx.send(data['results'][0]['data'])


# get_tree_expanded_from_root
bot.add_cog(FamilyCommands(bot))
# from cogs import error_handler
# error_handler.setup(bot)
bot.run("NDg4MjI3NzMyMDU3MjI3MjY1.Xv0XyA.ogegLsYZS3B2vvTgL18yxL1jkhY")
