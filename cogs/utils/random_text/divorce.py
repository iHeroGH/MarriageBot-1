from cogs import utils


class DivorceRandomText(utils.random_text.TextTemplate):

    @staticmethod
    @utils.random_text.get_random_valid_string
    def valid_target(instigator=None, target=None):
        return [
            "Sorry, {target.mention}, looks like you're single now. Congrats, {instigator.mention}!",
            "I hope you figure it out some day, but for now it looks like the two of you are divorced, {instigator.mention}, {target.mention}.",
            "At least you don't have to deal with {instigator.mention} any more, {target.mention}, right...?",
            "Not the happiest of news for you, {target.mention}, but it looks like {instigator.mention} just left you...",
            "You and {target.mention} are now divorced. I wish you luck in your lives.",
            "You and your partner are now divorced. I wish you luck in your lives.",
            "I hope you figure it out some day, but for now, you and your partner are divorced, {instigator.mention}.",
            "You just committed marriagen't.",
            "_Sad violin noises._",
        ]

    @staticmethod
    @utils.random_text.get_random_valid_string
    def instigator_is_unqualified(instigator=None, target=None):
        return [
            "Crazy idea, but you could try getting married first?",
            "It may seem like a stretch, but you need to marry someone before you can divorce them.",
            "Maybe try marrying them first?",
            "You're not married. Don't try to divorce strangers .",
            "Way to use your imagination, {instigator.mention}! But unfortunately for you, you need to be married to someone before you can divorce them.",
            "Sorry but you're too lonely to do that.",
        ]
